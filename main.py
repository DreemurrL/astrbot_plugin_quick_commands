"""AstrBot WebUI quick-command manager, backed by plugin_data JSON.

Targets AstrBot >=4.29 with Plugin Views + register_web_api bridge.
The commands are dynamic message listeners, not framework-registered commands.
The custom wake filter only activates when a saved rule matches. This prevents
nonmatching ordinary chat from being awakened by the dynamic listener.
Read the unmodified Plain message chain; AstrBot strips wake prefixes
from event.message_str after the waking check.
"""
from __future__ import annotations

import json
import os
import re
import uuid
import weakref
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


PLUGIN_NAME = "astrbot_plugin_quick_commands"
NAME_PATTERN = re.compile(r"^[\w\u4e00-\u9fff-]{1,30}$", re.UNICODE)
MESSAGE_PATTERN = re.compile(r"^\s*([/／]?)([^\s/／]+)(?:\s+([\s\S]*))?$")
# A conservative list of core/builtin commands; it is NOT a registry of all installed plugins.
RESERVED = {
    "help", "sid", "name", "reset", "stop", "new", "stats", "provider",
    "dashboard_update", "set", "unset", "plugin", "plugins", "op", "deop",
    "model", "history", "ls", "groupnew", "switch", "rename", "del",
    "persona", "llm", "quickcmd", "快捷管理",
}
MAX_RULES = 100
MAX_CONTENT = 16000
MAX_ALIASES = 12
REPLY_CHUNK = 1500


class QuickCommandWakeFilter(filter.CustomFilter):
    """Allow a message through AstrBot waking check only if a rule matches.

    AstrBot 4.29.1 checks handler filters in WakingCheckStage, before ordinary
    message handlers execute. An unconditional EventMessageType.ALL listener
    would otherwise wake the bot on every unprefixed group message.
    """
    instance_ref = None

    def filter(self, event: AstrMessageEvent, cfg) -> bool:
        instance = self.instance_ref() if self.instance_ref is not None else None
        return instance is not None and instance._match_event(event) is not None


class QuickCommands(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.storage_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "shortcuts.json"
        self.rules = self._read_rules()
        self.lookup = {}
        self._rebuild_lookup()
        QuickCommandWakeFilter.instance_ref = weakref.ref(self)
        context.register_web_api(f"/{PLUGIN_NAME}/rules", self.web_rules, ["GET"], "查看快捷指令")
        context.register_web_api(f"/{PLUGIN_NAME}/save", self.web_save, ["POST"], "保存快捷指令")
        context.register_web_api(f"/{PLUGIN_NAME}/delete", self.web_delete, ["POST"], "删除快捷指令")
        logger.info("快捷指令管理器已加载，规则 %d 条", len(self.rules))

    def _read_rules(self) -> list[dict]:
        if not self.storage_path.exists():
            return []
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
                raise ValueError("规则文件格式错误")
            # Stored by this plugin only; validate on load for manual edits too.
            rules = []
            for item in data["rules"][:MAX_RULES]:
                if isinstance(item, dict):
                    try:
                        rules.append(self._normalize(item, keep_id=True))
                    except ValueError as exc:
                        logger.warning("跳过无效快捷指令：%s", exc)
            return rules
        except Exception as exc:
            logger.error("读取快捷指令数据失败：%s", exc)
            return []  # Do NOT overwrite the possibly recoverable file on load.

    @staticmethod
    def _cmd(text: object) -> str:
        if not isinstance(text, str):
            raise ValueError("指令必须是文本")
        name = text.strip().lstrip("/／").strip()
        if not NAME_PATTERN.fullmatch(name):
            raise ValueError("指令名只能使用中文、字母、数字、下划线或连字符，长度 1~30")
        if name.casefold() in RESERVED:
            raise ValueError(f"指令 /{name} 属于系统保留指令，不能覆盖")
        return name

    def _normalize(self, item: dict, keep_id: bool) -> dict:
        if not isinstance(item, dict):
            raise ValueError("规则格式错误")
        name = self._cmd(item.get("name", ""))
        aliases_in = item.get("aliases", [])
        if isinstance(aliases_in, str):
            aliases_in = re.split(r"[,，\n]+", aliases_in)
        if not isinstance(aliases_in, list) or len(aliases_in) > MAX_ALIASES:
            raise ValueError(f"每条规则最多 {MAX_ALIASES} 个别名")
        aliases = []
        keys = {name.casefold()}
        for alias in aliases_in:
            if not isinstance(alias, str) or not alias.strip():
                continue
            alias = self._cmd(alias)
            key = alias.casefold()
            if key in keys:
                continue
            aliases.append(alias)
            keys.add(key)
        mode = item.get("mode", "text")
        if mode not in ("text", "txt"):
            raise ValueError("回复类型必须是 text 或 txt")
        content = item.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("回复内容不能为空")
        if len(content) > MAX_CONTENT:
            raise ValueError(f"回复内容不能超过 {MAX_CONTENT} 个字符")
        row_id = item.get("id") if keep_id else None
        if not isinstance(row_id, str) or not re.fullmatch(r"[0-9a-f]{32}", row_id):
            row_id = uuid.uuid4().hex
        return {
            "id": row_id,
            "name": name,
            "aliases": aliases,
            "mode": mode,
            "content": content.replace("\r\n", "\n"),
            "enabled": item.get("enabled", True) is not False,
            "admin_only": item.get("admin_only", False) is True,
            "accept_args": item.get("accept_args", False) is True,
            # Old 1.0.1 rules stay slash-only until user enables this switch.
            "allow_no_slash": item.get("allow_no_slash", False) is True,
        }

    @staticmethod
    def _check_unique(rows: list[dict]):
        names = {}
        for rule in rows:
            for name in [rule["name"], *rule["aliases"]]:
                key = name.casefold()
                if key in names:
                    raise ValueError(f"/{name} 已被另一条快捷指令占用")
                names[key] = rule["id"]

    def _rebuild_lookup(self):
        self.lookup = {
            name.casefold(): rule
            for rule in self.rules if rule["enabled"]
            for name in [rule["name"], *rule["aliases"]]
        }

    def _persist(self, rows: list[dict]):
        # Atomic replace: a crash during writing cannot produce half a JSON file.
        temp = self.storage_dir / f".{uuid.uuid4().hex}.tmp"
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump({"version": 1, "rules": rows}, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.storage_path)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
        self.rules = rows
        self._rebuild_lookup()

    async def web_rules(self):
        return json_response({"rules": self.rules, "storage": "data/plugin_data/" + PLUGIN_NAME + "/shortcuts.json"})

    async def web_save(self):
        data = await request.json(default={})
        if not isinstance(data, dict):
            return error_response("无效 JSON 数据", status_code=400)
        try:
            raw_id = data.get("id")
            existing_ids = {r["id"] for r in self.rules}
            if raw_id and raw_id not in existing_ids:
                raise ValueError("原规则不存在，请刷新页面")
            row = self._normalize(data, keep_id=bool(raw_id))
            rows = [r for r in self.rules if r["id"] != row["id"]]
            if len(rows) >= MAX_RULES:
                raise ValueError(f"最多创建 {MAX_RULES} 条规则")
            rows.append(row)
            self._check_unique(rows)
            self._persist(rows)
            return json_response({"saved": True, "rules": self.rules})
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except OSError as exc:
            logger.error("快捷指令保存出错：%s", exc)
            return error_response("写入存储文件失败", status_code=500)

    async def web_delete(self):
        data = await request.json(default={})
        row_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(row_id, str):
            return error_response("缺少规则 ID", status_code=400)
        rows = [r for r in self.rules if r["id"] != row_id]
        if len(rows) == len(self.rules):
            return error_response("原规则不存在，请刷新页面", status_code=404)
        try:
            self._persist(rows)
            return json_response({"deleted": True, "rules": self.rules})
        except OSError as exc:
            logger.error("快捷指令删除失败：%s", exc)
            return error_response("写入存储文件失败", status_code=500)

    @staticmethod
    def _original_command_text(event: AstrMessageEvent) -> str:
        """Use raw Plain components: event.message_str may have had '/' stripped.

        Do not concatenate outlines of non-Plain components into a command.
        Allow '@bot kfc' when it arrives as an At followed by a Plain.
        """
        components = event.get_messages()
        if components:
            return "".join(
                item.text for item in components if isinstance(item, Plain)
            ).strip()
        # Fallback for adapters which provide no raw component list.
        return (event.message_str or "").strip()

    def _match_event(self, event: AstrMessageEvent):
        """Return (rule, args) only on an allowed exact keyword match."""
        match = MESSAGE_PATTERN.fullmatch(self._original_command_text(event))
        if not match:
            return None
        slash, name, args = match.groups()
        rule = self.lookup.get(name.casefold())
        if rule is None:
            return None
        if not slash and not rule["allow_no_slash"]:
            return None
        args = args or ""
        if args and not rule["accept_args"]:
            return None
        if rule["admin_only"] and getattr(event, "role", "member") != "admin":
            return None
        return rule, args

    @filter.custom_filter(QuickCommandWakeFilter)
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """Reply only to matched slash or explicitly enabled bare shortcuts."""
        found = self._match_event(event)
        if found is None:
            return
        rule, args = found
        content = (
            rule["content"].replace("{args}", args.strip())
            if rule["accept_args"] else rule["content"]
        )
        for start in range(0, len(content), REPLY_CHUNK):
            yield event.plain_result(content[start:start + REPLY_CHUNK])
        event.stop_event()

    async def terminate(self):
        """Release the active reference when the plugin is unloaded."""
        ref = QuickCommandWakeFilter.instance_ref
        if ref is not None and ref() is self:
            QuickCommandWakeFilter.instance_ref = None
