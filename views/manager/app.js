const bridge = window.AstrBotPluginView;
const $ = (id) => document.getElementById(id);
let rules = [];
let editingId = null;
let busy = false;
const htmlEscape = (text) => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(text){const t=$('toast');t.textContent=text;t.hidden=false;clearTimeout(notify.timer);notify.timer=setTimeout(()=>{t.hidden=true;},3200);}
function render(){
  $('loading').hidden=true;$('rules').hidden=!rules.length;$('empty').hidden=!!rules.length;
  $('allNum').textContent=rules.length;
  $('activeNum').textContent=rules.filter(x=>x.enabled).length;
  $('aliasNum').textContent=rules.filter(x=>x.enabled).reduce((a,x)=>a+1+x.aliases.length,0);
  $('rules').innerHTML=rules.map(r=>`<div class="rule"><div class="ruleInfo"><span class="command">/${htmlEscape(r.name)}</span><span class="aliases">${r.aliases.map(x=>'/'+htmlEscape(x)).join(' · ')}</span><div class="snippet">${r.content ? htmlEscape(r.content.replace(/\s+/g,' ').slice(0,170)) : ''}</div><div style="margin-top:9px"><span class="tag ${r.enabled?'':'off'}">${r.enabled?'已启用':'已停用'}</span><span class="tag">${r.mode==='txt'?'TXT 文本':'固定文字'}</span>${r.admin_only?'<span class="tag off">仅管理员</span>':''}${r.allow_no_slash?'<span class="tag">可直接输入</span>':''}</div></div><div class="actionrow"><button class="btn ghost" data-action="edit" data-id="${r.id}">编辑</button><button class="btn ghost" data-action="toggle" data-id="${r.id}">${r.enabled?'停用':'启用'}</button><button class="btn ghost danger" data-action="delete" data-id="${r.id}">删除</button></div></div>`).join('');
}
async function load(){try{const data=await bridge.apiGet('rules');rules=data.rules||[];render();}catch(err){$('loading').textContent=`载入失败：${err.message||err}`;notify('无法加载数据，请检查插件日志。');}}
function openEditor(rule=null){
  editingId=rule?.id||null;$('editorTitle').textContent=rule?'编辑快捷指令':'新建快捷指令';
  $('name').value=rule?.name||'';$('aliases').value=rule?.aliases?.join(', ')||'';
  $('mode').value=rule?.mode||'text';$('content').value=rule?.content||'';
  $('enabled').checked=rule?.enabled??true;$('admin').checked=rule?.admin_only??false;$('args').checked=rule?.accept_args??false;$('noSlash').checked=rule?.allow_no_slash??false;
  $('file').value='';$('formError').hidden=true;updatePreview();$('editor').showModal();$('name').focus();
}
function closeEditor(){if(!busy)$('editor').close();}
function updatePreview(){const name=$('name').value.trim().replace(/^[/／]+/,'')||'指令';const preview=$('content').value.slice(0,320);const trigger=$('noSlash').checked?`/${name} 或 ${name}`:`/${name}`;$('previewText').textContent=`QQ 输入：${trigger}\n机器人回复：${preview||'（待填写）'}`;}
function getForm(){return{id:editingId||undefined,name:$('name').value,aliases:$('aliases').value.split(/[,，\n]+/).map(s=>s.trim()).filter(Boolean),mode:$('mode').value,content:$('content').value,enabled:$('enabled').checked,admin_only:$('admin').checked,accept_args:$('args').checked,allow_no_slash:$('noSlash').checked};}
async function save(data){return await bridge.apiPost('save',data);}
$('newBtn').addEventListener('click',()=>openEditor());
$('refreshBtn').addEventListener('click',load);
$('closeBtn').addEventListener('click',closeEditor);
$('cancelBtn').addEventListener('click',closeEditor);
$('name').addEventListener('input',updatePreview);$('content').addEventListener('input',updatePreview);$('noSlash').addEventListener('change',updatePreview);
$('file').addEventListener('change',async(e)=>{
  const file=e.target.files?.[0];if(!file)return;
  if(file.size>65536){$('formError').textContent='TXT 文件不能超过 64 KB';$('formError').hidden=false;return;}
  try{const text=await file.text();if(text.includes('\uFFFD'))throw Error('不是有效的 UTF-8 文件');if(text.length>16000)throw Error('文本不能超过 16000 字');
    $('content').value=text.replace(/^\uFEFF/,'');$('mode').value='txt';$('formError').hidden=true;updatePreview();notify('TXT 文件已读取，点击保存即可生效。');
  }catch(err){$('formError').textContent=err.message||String(err);$('formError').hidden=false;}
});
$('form').addEventListener('submit',async(e)=>{
  e.preventDefault();if(busy)return;busy=true;$('saveBtn').disabled=true;$('formError').hidden=true;
  try{const data=await save(getForm());rules=data.rules;$('editor').close();render();notify('保存成功，QQ 中立即生效。');}
  catch(err){$('formError').textContent=err.message||String(err);$('formError').hidden=false;}
  finally{busy=false;$('saveBtn').disabled=false;}
});
$('rules').addEventListener('click',async(e)=>{
  const btn=e.target.closest('button[data-action]');if(!btn||busy)return;const r=rules.find(x=>x.id===btn.dataset.id);if(!r)return;
  if(btn.dataset.action==='edit')return openEditor(r);
  if(btn.dataset.action==='delete'&&!confirm(`确认删除 /${r.name} 吗？`))return;
  busy=true;btn.disabled=true;
  try{const result=btn.dataset.action==='delete' ? await bridge.apiPost('delete',{id:r.id}):await save({...r,enabled:!r.enabled});rules=result.rules;render();notify(btn.dataset.action==='delete'?'规则已删除':'状态已更新');}
  catch(err){notify(`操作失败：${err.message||err}`);btn.disabled=false;}
  finally{busy=false;}
});
if(!bridge){$('loading').textContent='未检测到 AstrBot WebUI 插件页面桥接。请从 AstrBot 的扩展功能入口打开本页。';}
else {try{await bridge.ready();await load();}catch(err){$('loading').textContent='WebUI 桥接初始化失败：'+String(err);}}
