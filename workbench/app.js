(()=>{
  "use strict";
  const roles = [
    ["discovery","product-manager","产品经理","需求发现","定义场景、业务价值与验收条件","goal"],
    ["planning","project-manager","项目经理","迭代计划","拆分故事，协调依赖并安排迭代","calendar"],
    ["design","ux-designer","UI/UX 设计师","交互设计","交接关键操作、异常状态和设计稿","pen"],
    ["implement","pacs-developer","开发工程师","开发实现","实现领域规则、接口契约与测试","code"],
    ["verify","test-engineer","测试工程师","验收验证","复核临床场景，记录回归与缺陷证据","check"],
    ["release","ops-engineer","运维工程师","发布运维","核对发布条件、监控与回滚记录","pulse"]
  ];
  const domains = [
    ["检查登记","检查申请","以检查号关联申请、预约和检查状态。","检查已登记","核对来自 RIS 的检查申请与设备工作列表。"],
    ["影像归档","影像检查","以 Study、Series 和 SOP Instance UID 识别影像层级。","影像已归档","检查重复传输后，实例数量与检索结果是否一致。"],
    ["阅片诊断","阅片任务","组织阅片工作列表、序列加载和诊断协作。","阅片任务已领取","观察序列加载失败时，医生能否恢复当前阅片任务。"],
    ["报告审核","诊断报告","维护报告版本、签署状态和审核约束。","报告已审核","确认审核后修改报告所产生的版本与重新签署要求。"],
    ["结果分发","分发任务","跟踪审核结果的投递、回执与重试。","分发已确认","模拟回执超时，核对重试时使用的报告版本。"],
    ["平台运维","发布批次","管理版本发布、运行观测和恢复。","版本已发布","演练异常版本的回滚，并核对关键服务的恢复情况。"]
  ];
  const paths = {overview:"M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",board:"M3 4h18v16H3z M9 4v16 M15 4v16",map:"M9 3h6v5H9z M3 16h6v5H3z M15 16h6v5h-6z M12 8v4 M6 16v-4h12v4",goal:"M12 21a9 9 0 1 1 .1 0 M12 17a5 5 0 1 1 .1 0 M12 12l7-7",calendar:"M3 6h18v15H3z M3 11h18 M7 3v5 M17 3v5",pen:"M4 20l5-1L21 7l-4-4L5 15z M14 6l4 4",code:"M8 6l-6 6 6 6 M16 6l6 6-6 6 M14 3l-4 18",check:"M12 2l8 4v6q0 6-8 10-8-4-8-10V6z M8 12l3 3 5-6",pulse:"M2 12h5l3-8 4 16 3-8h5",plus:"M12 5v14 M5 12h14",arrow:"M5 12h14 M14 7l5 5-5 5",layers:"M2 8l10-5 10 5-10 5z M2 12l10 5 10-5 M2 16l10 5 10-5"};
  const icon=(key)=>`<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[key]}"/></svg>`;
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const $=s=>document.querySelector(s);
  const state={items:[],view:"overview",role:"",sprint:"",domain:"",query:"",detail:null};
  const names={overview:"工作总览",board:"迭代看板",map:"领域地图",role:"角色工作台"};
  const stageName=id=>id==="done"?"已交付":roles.find(r=>r[0]===id)?.[3]||id;
  const handoffs={
    discovery:["用户故事与验收条件","作为哪一类用户，希望完成什么操作？怎样观察到成功？","合成输入、预期结果，或需求条目位置"],
    planning:["迭代目标与依赖","本轮切片、上下游依赖、可用容量和完成定义","迭代计划位置、依赖责任人和联调窗口"],
    design:["交互方案与状态","关键路径、空状态、错误恢复及键盘操作","设计稿版本、原型位置和走查观察"],
    implement:["实现与领域约束","变更入口、聚合规则、兼容与重试行为","差异位置、测试命令和结果"],
    verify:["验收范围与实测结果","记录版本、环境、预期与实际，以及剩余缺口","合成场景、实测日志或缺陷编号"],
    release:["发布范围与恢复结果","记录授权环境、交付版本、观测及回滚条件","变更单、监控记录、演练或实际恢复结果"]
  };
  const option=(v,selected,label=v)=>`<option value="${esc(v)}"${v===selected?" selected":""}>${esc(label)}</option>`;
  const empty=msg=>`<p class="empty">${esc(msg)}</p>`;
  let ticket=0;
  async function api(path,method="GET",body) {
    const response=await fetch(path,{method,headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});
    const result=await response.json();
    if(!response.ok) {const error=new Error(result.error||"请求失败");error.status=response.status;throw error;}
    return result;
  }
  function notice(message) {const el=$("#notice");el.textContent=message;el.hidden=!message;}
  async function refresh(){
    const n=++ticket;
    const board=await api("/api/board");
    if(n!==ticket)return;
    state.items=board.items;render();
  }
  function nav(){
    const button=(label,attr,value,svg,active)=>`<button class="nav ${active?"active":""}" data-${attr}="${value}" ${active?'aria-current="page"':""}>${icon(svg)}${label}</button>`;
    $("#nav").innerHTML=`<h3>工作空间</h3>${["overview","board","map"].map(v=>button(names[v],"view",v,v,state.view===v)).join("")}
      <h3>角色工作台</h3>${roles.map(r=>button(r[2],"role",r[1],r[5],state.view==="role"&&state.role===r[1])).join("")}`;
  }
  function card(i) {
    return `<button class="task" data-item="${esc(i.id)}"><span class="task-top"><small>${esc(i.domain)}</small><b class="priority ${esc(i.priority)}">${esc(i.priority)}</b></span><strong>${esc(i.title)}</strong><span class="task-bottom">${esc(i.sprint)} <span>${i.blocked?"● 已阻塞":stageName(i.stage)}</span></span></button>`;
  }
  function heading(title,sub,action=true){
    return `<div class="heading"><div><h1>${esc(title)}</h1><p>${esc(sub)}</p></div>${action?`<button class="primary" data-new>${icon("plus")}新建工作项</button>`:""}</div>`;
  }
  function overview(){
    const items=state.items,counts=[items.length,items.filter(i=>!i.completed&&!i.blocked).length,items.filter(i=>i.blocked).length,items.filter(i=>i.completed).length];
    return heading("工作总览","PACS 产品研发、迭代协作与版本交付。")+
      `<div class="metrics">${["全部工作项","进行中","已阻塞","已交付"].map((v,i)=>`<div><span><i class="signal s${i}"></i>${v}</span><b>${counts[i]}</b></div>`).join("")}</div>
      <div class="section-title"><h2>角色工作台</h2><span>按当前负责角色进入</span></div>
      <div class="role-grid">${roles.map((r,i)=>`<button class="role-card c${i}" data-role="${r[1]}"><div class="role-top"><span class="symbol">${icon(r[5])}</span><small>${r[3]}</small></div><h3>${r[2]}</h3><p>${r[4]}</p><footer><span>${items.filter(x=>x.role===r[1]&&!x.completed).length} 项待处理</span>${icon("arrow")}</footer></button>`).join("")}</div>
      <div class="section-title"><h2>交付流程</h2><button class="link" data-view="board">进入迭代看板 →</button></div>
      <div class="pipeline">${roles.map(r=>`<button data-role="${r[1]}">${icon(r[5])}<span>${r[3]}</span></button>`).join('<i>›</i>')}</div>`;
  }
  function filtered(){
    return state.items.filter(x=>(!state.sprint||x.sprint===state.sprint)&&(!state.domain||x.domain===state.domain)&&(!state.query||x.title.toLowerCase().includes(state.query.toLowerCase())));
  }
  function lanes(){
    const items=filtered();
    const extra=[...new Set(items.filter(i=>!i.completed&&!roles.some(r=>r[0]===i.stage)).map(i=>i.stage))];
    return [...roles.map(r=>[r[0],r[3]]),...extra.map(id=>[id,id]),["done","已交付"]].map(([id,label],j)=>{
      const entries=items.filter(i=>id==="done"?i.completed:!i.completed&&i.stage===id);
      return `<section class="lane"><h3><i class="signal s${j%4}"></i>${label}<small>${entries.length}</small></h3>${entries.map(card).join("")||empty("暂无工作项")}</section>`;
    }).join("");
  }
  function board(){
    const sprints=[...new Set(state.items.map(i=>i.sprint))].sort(),d=[...new Set([...domains.map(x=>x[0]),...state.items.map(i=>i.domain)])];
    return heading("迭代看板","按迭代和限界上下文查看故事，打开工作项完成交接。")+
      `<div class="filters"><label>迭代<select id="sprint-filter">${option("",state.sprint,"全部迭代")}${sprints.map(x=>option(x,state.sprint)).join("")}</select></label><label>上下文<select id="domain-filter">${option("",state.domain,"全部上下文")}${d.map(x=>option(x,state.domain)).join("")}</select></label><label>搜索<input id="query" type="search" placeholder="工作项标题" value="${esc(state.query)}"></label></div><div class="lanes" id="lanes">${lanes()}</div>`;
  }
  function mapPage(){
    return heading("领域地图","按业务边界梳理聚合、领域事件和跨角色验收场景。",false)+
      '<section class="context-flow"><h2>修订报告重新分发</h2><p><b>报告审核</b> 签发新版本 → <b>结果分发</b> 按版本和目的端投递 → <b>接收端</b> 确认接收</p><small>验收时分别核对签发履历、重试记录和目标端展示版本。</small></section>'+
      `<div class="domain-grid">${domains.map(d=>`<article class="domain"><span class="symbol">${icon("layers")}</span><h2>${d[0]}</h2><p>${d[2]}</p><dl><dt>建模对象</dt><dd>${d[1]}</dd><dt>事件示例</dt><dd>${d[3]}</dd></dl><p>${d[4]}</p><button class="link" data-domain-board="${d[0]}">查看工作项 →</button></article>`).join("")}</div>`;
  }
  function rolePage(){
    const r=roles.find(x=>x[1]===state.role),items=state.items.filter(i=>i.role===r[1]&&!i.completed);
    return heading(r[2]+"工作台",r[4])+
      `<div class="role-banner"><span class="symbol">${icon(r[5])}</span><div><small>负责阶段</small><h2>${r[3]}</h2></div><b>${items.length}<small> 项待处理</small></b></div>
      <div class="section-title"><h2>待处理工作项</h2><button class="link" data-view="board">查看全部迭代 →</button></div><div class="queue">${items.map(card).join("")||empty("当前没有交接到该角色的工作项。")}</div>`;
  }
  function render(){
    nav();$("#crumb").textContent=state.view==="role"?roles.find(r=>r[1]===state.role)[2]:names[state.view];
    $("#page").innerHTML=({overview,board,map:mapPage,role:rolePage})[state.view]();
  }
  function show(content){
    const dlg=$("#dialog");
    $("#dialog-body").innerHTML=`<button type="button" class="close" data-close aria-label="关闭">×</button>${content}<p class="form-error" role="alert" id="form-error"></p>`;
    if(!dlg.open)dlg.showModal();
  }
  const priorities=(p)=>["P1","P2","P3"].map(x=>option(x,p)).join("");
  function newItem(){
    state.detail=null;
    show(`<h2>新建工作项</h2><p class="dim">从需求发现开始，由产品经理接手。</p><form id="new-form"><label>故事标题<input name="title" required maxlength="240" placeholder="例如：审核报告后向 RIS 分发最新版本"></label>
      <label>限界上下文<select name="domain">${domains.map(d=>option(d[0],state.domain)).join("")}</select></label>
      <div class="pair"><label>迭代<input name="sprint" value="${esc(state.sprint||"待规划")}" maxlength="80" required></label><label>优先级<select name="priority">${priorities("P2")}</select></label></div><button class="primary">创建工作项</button></form>`);
  }
  const outcomes={pass:"通过并交接",blocked:"登记阻塞",fail:"登记失败并返工"};
  function detail(i){
    state.detail=i;
    const fields=handoffs[i.stage]||["结论","实际结果或阻塞原因","证据位置或观察值"];
    show(`<div class="over">${esc(i.domain)} · ${esc(i.priority)} · ${esc(i.id)}</div><h2>${esc(i.title)}</h2><p class="dim">${esc(i.sprint)}　/　${esc(stageName(i.stage))}${i.blocked?"　·　已阻塞":""}</p>
      ${!i.completed?`<section class="brief"><b>本阶段交付要求</b><p>${esc(i.deliverable)}</p><details><summary>角色与执行指引</summary><pre>${esc(i.role_text)}\n\n${esc(i.skill_text)}</pre></details></section>
      <form id="checkpoint-form"><h3>阶段交接</h3><label>结果<select name="outcome">${Object.entries(outcomes).map(([v,n])=>option(v,"pass",n)).join("")}</select></label>
      <label>${fields[0]}<textarea name="summary" required rows="2" placeholder="${fields[1]}"></textarea></label>
      <label>证据（每行一项）<textarea name="evidence" required rows="2" placeholder="${fields[2]}"></textarea></label><button class="primary">保存交接</button></form>
      <details><summary>调整迭代与优先级</summary><form id="plan-form"><div class="pair"><label>迭代<input required name="sprint" value="${esc(i.sprint)}"></label><label>优先级<select name="priority">${priorities(i.priority)}</select></label></div><button class="secondary">保存排期</button></form></details>`:""}
      <section><h3>交付记录 · ${i.history.length}</h3>${[...i.history].reverse().map(h=>`<article class="event"><b>${stageName(h.stage)} · ${esc(outcomes[h.outcome])}</b><small>${esc(new Date(h.recorded).toLocaleString("zh-CN",{hour12:false}))}</small><p>${esc(h.summary)}</p><ul>${h.evidence.map(e=>`<li>${esc(e)}</li>`).join("")}</ul></article>`).join("")||empty("尚未登记阶段结果。")}</section>`);
  }
  const itemUrl=id=>"/api/items/"+encodeURIComponent(id);
  document.addEventListener("click",async e=>{
    const b=e.target.closest("button");if(!b)return;
    try{
      if(b.hasAttribute("data-close"))$("#dialog").close();
      else if(b.id==="refresh"){await refresh();notice("");}
      else if(b.dataset.view){state.view=b.dataset.view;state.domain="";state.sprint="";state.query="";render();}
      else if(b.dataset.role){state.role=b.dataset.role;state.view="role";render();}
      else if(b.dataset.domainBoard){state.domain=b.dataset.domainBoard;state.sprint="";state.query="";state.view="board";render();}
      else if(b.hasAttribute("data-new"))newItem();
      else if(b.dataset.item)detail(await api(itemUrl(b.dataset.item)));
      else if(b.hasAttribute("data-reload-item"))detail(await api(itemUrl(state.detail.id)));
    }catch(err){notice(err.message);}
  });
  document.addEventListener("input",e=>{
    const keys={"sprint-filter":"sprint","domain-filter":"domain",query:"query"};
    if(keys[e.target.id]){state[keys[e.target.id]]=e.target.value;$("#lanes").innerHTML=lanes();}
  });
  document.addEventListener("submit",async e=>{
    e.preventDefault();
    const form=e.target,btn=form.querySelector("button"),v=Object.fromEntries(new FormData(form));
    btn.disabled=true;
    try{
      let result;
      if(form.id==="new-form")result=await api("/api/items","POST",v);
      else {
        const i=state.detail;
        if(form.id==="plan-form")result=await api(itemUrl(i.id),"PATCH",{...v,revision:i.revision});
        else result=await api(itemUrl(i.id)+"/checkpoint","POST",{...v,stage:i.stage,revision:i.revision,evidence:v.evidence.split(/\r?\n/).map(s=>s.trim()).filter(Boolean)});
      }
      detail(result);await refresh();notice("");
    }catch(err){
      const el=$("#form-error");el.textContent=err.message;
      if(err.status===409){const reload=document.createElement("button");reload.type="button";reload.dataset.reloadItem="";reload.textContent="重新读取最新工作项";el.append(" ",reload);}
    }finally{btn.disabled=false;}
  });
  refresh().catch(err=>{nav();$("#page").textContent="无法读取工作项，请刷新数据重试。";notice(err.message);});
})();
