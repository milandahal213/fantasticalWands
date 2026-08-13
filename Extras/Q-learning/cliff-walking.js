const Cliff = (function(){
  const ROWS=4, COLS=12;
  const START=idx(ROWS-1,0), GOAL=idx(ROWS-1,COLS-1);
  function idx(r,c){ return r*COLS+c; }
  function rc(i){ return [Math.floor(i/COLS), i%COLS]; }
  const CLIFF=new Set();
  for(let c=1;c<COLS-1;c++) CLIFF.add(idx(ROWS-1,c));

  const DELTA=[[-1,0],[1,0],[0,-1],[0,1]];
  const NAMES=['up','down','left','right'];
  const ARROWS=['↑','↓','←','→'];
  const ACTION_DEG=[-90,90,180,0];

  let ALPHA=0.5, GAMMA=0.9, EPS=0.1;
  let stepPenalty=-1, cliffPenalty=-100, goalReward=0;
  let speedLevel=5;
  const MAXSTEPS=200;

  let algo='ql';
  let Qql=Array.from({length:ROWS*COLS},()=>[0,0,0,0]);
  let Qsarsa=Array.from({length:ROWS*COLS},()=>[0,0,0,0]);
  function curQ(){ return algo==='ql' ? Qql : Qsarsa; }

  let episodesQL=0, episodesSARSA=0;
  let isAnimating=false;
  let agentPos=null;
  let facingDeg=0;
  let frameTick=0;
  let comparePathsData=null;
  let logLines=[];
  let logIdCounter=0;
  let expandedLogId=null;
  let epStepCount=0, epExploreCount=0;

  function argmax(a){ let bi=0; for(let i=1;i<a.length;i++){ if(a[i]>a[bi]) bi=i; } return bi; }
  function epsGreedy(q,s){
    const explore=Math.random()<EPS;
    const a = explore ? Math.floor(Math.random()*4) : argmax(q[s]);
    return {a, explore};
  }

  function doStep(state,action){
    const [r,c]=rc(state);
    const [dr,dc]=DELTA[action];
    let nr=r+dr, nc=c+dc;
    if(nr<0||nr>=ROWS||nc<0||nc>=COLS){ nr=r; nc=c; }
    const next=idx(nr,nc);
    if(CLIFF.has(next)){
      return {next:START, reward:cliffPenalty, done:false, fell:true};
    }
    if(next===GOAL){
      return {next, reward:goalReward, done:true, fell:false};
    }
    return {next, reward:stepPenalty, done:false, fell:false};
  }

  function setParam(name,value){
    const v=parseFloat(value);
    if(name==='ALPHA'){ ALPHA=v; document.getElementById('cliff-alpha-out').textContent=v.toFixed(2); }
    if(name==='GAMMA'){ GAMMA=v; document.getElementById('cliff-gamma-out').textContent=v.toFixed(2); drawGammaChart(); }
    if(name==='EPS'){ EPS=v; document.getElementById('cliff-eps-out').textContent=v.toFixed(2); }
  }
  function setSpeed(v){ speedLevel=parseInt(v); document.getElementById('cliff-speed-out').textContent=speedLevel; }
  function getDelay(){ return 260-speedLevel*22; }
  function setReward(name,val){
    const v=parseFloat(val);
    if(name==='stepPenalty') stepPenalty=v;
    if(name==='cliffPenalty') cliffPenalty=v;
    if(name==='goalReward') goalReward=v;
  }

  function drawGammaChart(){
    const el=document.getElementById('cliff-gamma-chart');
    if(!el) return;
    const n=12, w=176, h=54, padB=12, padT=4;
    let pts='';
    for(let i=0;i<=n;i++){
      const x=(i/n)*w;
      const y=padT+(1-Math.pow(GAMMA,i))*(h-padT-padB);
      pts+=(i===0?'M':'L')+x.toFixed(1)+' '+y.toFixed(1)+' ';
    }
    el.innerHTML='<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">discount over distance (&gamma;<sup>n</sup>)</div>'+
      '<svg viewBox="0 0 '+w+' '+h+'" style="width:100%;height:'+h+'px;display:block;">'+
      '<path d="'+pts+'" fill="none" stroke="var(--accent)" stroke-width="1.4"/>'+
      '<text x="0" y="'+h+'" font-size="8" fill="var(--text-muted)">0</text>'+
      '<text x="'+(w-14)+'" y="'+h+'" font-size="8" fill="var(--text-muted)">'+n+' steps</text>'+
      '</svg>';
  }

  function setAlgo(a){
    algo=a;
    comparePathsData=null;
    document.getElementById('cliff-algo-ql-btn').classList.toggle('active', a==='ql');
    document.getElementById('cliff-algo-sarsa-btn').classList.toggle('active', a==='sarsa');
    msg('Now training and viewing '+(a==='ql'?'Q-learning':'SARSA')+'.');
    render();
  }

  function resetAll(){
    if(isAnimating){ msg('Hang on for the current run to finish.'); return; }
    Qql=Array.from({length:ROWS*COLS},()=>[0,0,0,0]);
    Qsarsa=Array.from({length:ROWS*COLS},()=>[0,0,0,0]);
    episodesQL=0; episodesSARSA=0;
    logLines=[]; expandedLogId=null;
    comparePathsData=null;
    agentPos=null; facingDeg=0;
    epStepCount=0; epExploreCount=0;
    msg('Both Q-tables reset.');
    render();
  }

  function train(){
    if(isAnimating){ msg('Hang on for the current run to finish.'); return; }
    const el=document.getElementById('cliff-episode-input');
    const n=parseInt(el.value,10)||0;
    if(n<=0){ msg('Enter a number of episodes, then click Train.'); return; }
    comparePathsData=null;
    if(n===1){ runEpisodeAnimated(); }
    else { trainBulk(n); }
  }

  function trainBulk(n){
    const q=curQ();
    let fellCount=0, reachedCount=0;
    epStepCount=0; epExploreCount=0;
    for(let e=0;e<n;e++){
      let s=START;
      let {a,explore}=epsGreedy(q,s);
      let t=0, done=false;
      while(!done && t<MAXSTEPS){
        epStepCount++; if(explore) epExploreCount++;
        const {next,reward,done:d,fell}=doStep(s,a);
        if(fell) fellCount++;
        if(algo==='sarsa'){
          const {a:aNext, explore:exploreNext}=epsGreedy(q,next);
          q[s][a]+=ALPHA*(reward+GAMMA*q[next][aNext]-q[s][a]);
          s=next; a=aNext; explore=exploreNext;
        } else {
          const maxNext=Math.max(...q[next]);
          q[s][a]+=ALPHA*(reward+GAMMA*maxNext-q[s][a]);
          s=next;
          ({a,explore}=epsGreedy(q,s));
        }
        done=d; t++;
        if(d) reachedCount++;
      }
      if(algo==='ql') episodesQL++; else episodesSARSA++;
    }
    logLines=['Ran '+n+' episodes of '+(algo==='ql'?'Q-learning':'SARSA')+'. Reached the goal '+reachedCount+'/'+n+' times, fell off the cliff '+fellCount+' times total.'];
    agentPos=null;
    msg('Trained. Episodes so far — Q-learning: '+episodesQL+', SARSA: '+episodesSARSA+'.');
    render();
  }

  function runEpisodeAnimated(){
    if(isAnimating){ msg('Hang on for the current run to finish.'); return; }
    isAnimating=true;
    logLines=[];
    epStepCount=0; epExploreCount=0;
    const q=curQ();
    let s=START;
    let {a,explore}=epsGreedy(q,s);
    let t=0;
    agentPos=s;
    render();

    function step(){
      if(t>=MAXSTEPS){
        isAnimating=false;
        if(algo==='ql') episodesQL++; else episodesSARSA++;
        agentPos=null;
        msg('Ran out of steps. Episodes so far — Q-learning: '+episodesQL+', SARSA: '+episodesSARSA+'.');
        render();
        return;
      }
      setTimeout(()=>{
        epStepCount++; if(explore) epExploreCount++;
        const before=q[s][a];
        const [r,c]=rc(s);
        const {next,reward,done,fell}=doStep(s,a);
        const [nr,nc]=rc(next);
        let after, nextVals, maxNext, targetLabel, usedAction=null, usedExplore=null;
        if(algo==='sarsa'){
          const picked=epsGreedy(q,next);
          usedAction=picked.a; usedExplore=picked.explore;
          nextVals=q[next].slice();
          maxNext=q[next][usedAction];
          q[s][a]+=ALPHA*(reward+GAMMA*maxNext-q[s][a]);
          after=q[s][a];
          facingDeg=ACTION_DEG[a];
          logLines.unshift({id:logIdCounter++, algo, r, c, nr, nc, action:NAMES[a], reward, alpha:ALPHA, gamma:GAMMA, before, after, nextVals, maxNext, explore, usedAction:NAMES[usedAction], usedExplore, fell});
          s=next; a=picked.a; explore=picked.explore;
        } else {
          nextVals=q[next].slice();
          maxNext=Math.max(...nextVals);
          q[s][a]+=ALPHA*(reward+GAMMA*maxNext-q[s][a]);
          after=q[s][a];
          facingDeg=ACTION_DEG[a];
          logLines.unshift({id:logIdCounter++, algo, r, c, nr, nc, action:NAMES[a], reward, alpha:ALPHA, gamma:GAMMA, before, after, nextVals, maxNext, explore, usedAction:null, usedExplore:null, fell});
          s=next;
          ({a,explore}=epsGreedy(q,s));
        }
        logLines=logLines.slice(0,8);
        agentPos=s;
        t++;
        render();
        if(done){
          isAnimating=false;
          if(algo==='ql') episodesQL++; else episodesSARSA++;
          agentPos=null;
          msg('Reached the goal after '+t+' moves. Episodes so far — Q-learning: '+episodesQL+', SARSA: '+episodesSARSA+'.');
          render();
          return;
        }
        step();
      }, getDelay());
    }
    step();
  }

  function greedyPath(q, maxLen){
    const path=[START];
    let s=START;
    const seen=new Set();
    for(let t=0;t<maxLen;t++){
      if(s===GOAL) break;
      const a=argmax(q[s]);
      const key=s+'-'+a;
      if(seen.has(key)) break;
      seen.add(key);
      const {next,done,fell}=doStep(s,a);
      path.push(next);
      s=next;
      if(fell) break;
      if(done) break;
    }
    return path;
  }

  function walkGreedy(){
    if(isAnimating){ msg('Hang on for the current run to finish.'); return; }
    const q=curQ();
    if((algo==='ql'?episodesQL:episodesSARSA)===0){ msg('Train this algorithm first.'); return; }
    comparePathsData=null;
    const path=greedyPath(q, 60);
    isAnimating=true;
    let i=0;
    function tick(){
      if(i>=path.length){
        isAnimating=false;
        agentPos=null;
        const success=path[path.length-1]===GOAL;
        msg(success ? 'Reached the goal in '+(path.length-1)+' steps.' : 'Stopped — hit the cliff, a loop, or ran out of steps. Train more and try again.');
        render();
        return;
      }
      if(i>0){
        const [r0,c0]=rc(path[i-1]), [r1,c1]=rc(path[i]);
        if(r1<r0) facingDeg=-90; else if(r1>r0) facingDeg=90; else if(c1<c0) facingDeg=180; else facingDeg=0;
      }
      agentPos=path[i];
      render();
      i++;
      setTimeout(tick, getDelay());
    }
    tick();
  }

  function comparePaths(){
    if(isAnimating){ msg('Hang on for the current run to finish.'); return; }
    if(episodesQL===0 || episodesSARSA===0){ msg('Train both Q-learning and SARSA at least a little first, then compare.'); return; }
    agentPos=null;
    comparePathsData={
      ql: greedyPath(Qql, 60),
      sarsa: greedyPath(Qsarsa, 60)
    };
    msg('Blue = Q-learning’s greedy route. Green = SARSA’s greedy route.');
    render();
  }

  function msg(t){ document.getElementById('cliff-msg').textContent=t; }

  function nextValsBarChart(nextVals, maxNext){
    const w=200,h=64,baseline=34;
    const maxAbs=Math.max(1, ...nextVals.map(v=>Math.abs(v)));
    const scale=24/maxAbs;
    const labels=['U','D','L','R'];
    const barW=32, gap=16;
    let bars='';
    for(let i=0;i<4;i++){
      const v=nextVals[i];
      const bh=Math.max(1,Math.abs(v)*scale);
      const x=12+i*(barW+gap);
      const y = v>=0 ? baseline-bh : baseline;
      const isMax = v===maxNext;
      const color = isMax ? 'var(--accent)' : 'var(--text-muted)';
      bars+='<rect x="'+x+'" y="'+y+'" width="'+barW+'" height="'+bh+'" fill="'+color+'" opacity="'+(isMax?1:0.5)+'" rx="2"/>';
      bars+='<text x="'+(x+barW/2)+'" y="'+(h-3)+'" text-anchor="middle" font-size="8" fill="var(--text-muted)">'+labels[i]+'</text>';
      bars+='<text x="'+(x+barW/2)+'" y="'+(v>=0? y-3 : y+bh+9)+'" text-anchor="middle" font-size="7.5" fill="'+color+'">'+v.toFixed(2)+'</text>';
    }
    return '<svg viewBox="0 0 '+w+' '+h+'" style="width:100%;max-width:220px;height:64px;display:block;margin:4px 0 2px;">'+
      '<line x1="0" y1="'+baseline+'" x2="'+w+'" y2="'+baseline+'" stroke="var(--border)" stroke-width="1"/>'+bars+'</svg>';
  }

  function toggleLogDetail(id){
    expandedLogId = (expandedLogId===id) ? null : id;
    render();
  }

  function logHtml(){
    return logLines.map(entry=>{
      if(typeof entry==='string'){
        return '<div>'+entry+'</div>';
      }
      const expanded=(entry.id===expandedLogId);
      const sign=entry.reward>=0?'+':'';
      const modeTag = entry.explore
        ? '<span style="color:var(--goal);font-weight:700;font-size:9px;letter-spacing:0.3px;">EXPLORE</span>'
        : '<span style="color:var(--accent);font-weight:700;font-size:9px;letter-spacing:0.3px;">EXPLOIT</span>';
      const fellTag = entry.fell ? ' <span style="color:var(--danger);font-weight:700;font-size:9px;">FELL OFF CLIFF</span>' : '';
      const summary=modeTag+'  ['+entry.algo.toUpperCase()+']  ('+(entry.r+1)+','+(entry.c+1)+') → '+entry.action+
        '  reward '+sign+entry.reward.toFixed(1)+'  Q: '+entry.before.toFixed(2)+' → '+entry.after.toFixed(2)+fellTag;
      let detail='';
      if(expanded){
        const gm=entry.gamma*entry.maxNext;
        const target=entry.reward+gm;
        const tdError=target-entry.before;
        const alphaErr=entry.alpha*tdError;
        const rewardSpan='<span style="color:var(--success);font-weight:600;">'+entry.reward.toFixed(3)+'</span>';
        const futureSpan='<span style="color:var(--accent);font-weight:600;">'+gm.toFixed(3)+'</span>';
        const futureTermLabel = entry.algo==='sarsa'
          ? '&gamma; &times; Q(s&prime;,a&prime;) (value of the action actually taken next)'
          : '&gamma; &times; max(Q(s&prime;)) (value of the best possible next action)';
        const gmFormula='<span style="color:var(--accent);font-weight:600;">'+entry.gamma.toFixed(2)+' &times; '+entry.maxNext.toFixed(3)+'</span>';
        const sarsaNote = entry.algo==='sarsa'
          ? '<br>Next action actually chosen: <strong>'+entry.usedAction+'</strong> ('+(entry.usedExplore?'<span style="color:var(--goal);">exploratory</span>':'<span style="color:var(--accent);">greedy</span>')+')'
          : '';
        detail='<div style="margin:4px 0 8px 12px;padding:10px 12px;background:var(--surface-2);border-left:2px solid var(--accent);border-radius:4px;font-size:10.5px;line-height:1.8;">'+
          'Moving from ('+(entry.r+1)+','+(entry.c+1)+') to ('+(entry.nr+1)+','+(entry.nc+1)+') via <strong>'+entry.action+'</strong>'+sarsaNote+'<br>'+
          'Q(s,a) before &nbsp;= '+entry.before.toFixed(3)+'<br>'+
          '<span style="color:var(--success);">reward (real, this step)</span> = '+rewardSpan+'<br>'+
          'next-state Q-values — the one used is highlighted:'+
          nextValsBarChart(entry.nextVals, entry.maxNext)+
          '<span style="color:var(--accent);">'+futureTermLabel+'</span> = '+gmFormula+' = '+futureSpan+'<br>'+
          'target = '+rewardSpan+' + '+futureSpan+' = '+target.toFixed(3)+'<br>'+
          'TD error = target &minus; before = '+target.toFixed(3)+' &minus; '+entry.before.toFixed(3)+' = '+tdError.toFixed(3)+'<br>'+
          '&alpha; &times; TD error = '+entry.alpha.toFixed(2)+' &times; '+tdError.toFixed(3)+' = '+alphaErr.toFixed(3)+'<br>'+
          'Q(s,a) after = before + &alpha;&times;error = '+entry.before.toFixed(3)+' + '+alphaErr.toFixed(3)+' = <strong>'+entry.after.toFixed(3)+'</strong>'+
          '</div>';
      }
      return '<div style="cursor:pointer;" onclick="Cliff.toggleLogDetail('+entry.id+')">'+summary+
        ' <span style="color:var(--text-muted);font-size:9px;">'+(expanded?'&#9650; hide math':'&#9660; show math')+'</span></div>'+detail;
    }).join('');
  }

  function pathOverlaySvg(){
    if(!comparePathsData) return '';
    function pathToPoints(path){
      return path.map(i=>{ const [r,c]=rc(i); return [(c+0.5)/COLS*100, (r+0.5)/ROWS*100]; });
    }
    function toD(points){
      return points.map((p,idx)=>(idx===0?'M':'L')+p[0].toFixed(2)+' '+p[1].toFixed(2)).join(' ');
    }
    const qlPts=pathToPoints(comparePathsData.ql);
    const saPts=pathToPoints(comparePathsData.sarsa);
    return '<path d="'+toD(qlPts)+'" fill="none" stroke="var(--accent)" stroke-width="1.4" stroke-dasharray="3 2" opacity="0.9"/>'+
      '<path d="'+toD(saPts)+'" fill="none" stroke="var(--success)" stroke-width="1.4" stroke-dasharray="3 2" opacity="0.9"/>';
  }

  function render(){
    frameTick++;
    const q=curQ();
    const eps=(algo==='ql'?episodesQL:episodesSARSA);
    const exploreRate = epStepCount>0 ? Math.round(epExploreCount/epStepCount*100) : null;
    const exploreStat = exploreRate!==null
      ? '<span>Exploring: '+epExploreCount+'/'+epStepCount+' steps this run ('+exploreRate+'%, target '+Math.round(EPS*100)+'%)</span>'
      : '';
    document.getElementById('cliff-stats').innerHTML =
      '<span>Active: '+(algo==='ql'?'Q-learning':'SARSA')+'</span>'+
      '<span>Q-learning episodes: '+episodesQL+'</span>'+
      '<span>SARSA episodes: '+episodesSARSA+'</span>'+
      exploreStat;

    const gridEl=document.getElementById('cliff-grid');
    gridEl.style.gridTemplateColumns='repeat('+COLS+',1fr)';
    gridEl.style.aspectRatio=COLS+'/'+ROWS;
    let html='';
    for(let i=0;i<ROWS*COLS;i++){
      const isCliff=CLIFF.has(i);
      const isStart=i===START;
      const isGoal=i===GOAL;
      const isAgent=agentPos===i;
      let style='', inner='';
      if(isCliff){
        style='background:var(--danger-bg);border-color:var(--danger);';
        inner='<span style="font-size:12px;color:var(--danger);">&#9760;</span>';
      } else if(isGoal){
        style='background:var(--goal-bg);border:2px solid var(--goal);';
        inner='<span style="color:var(--goal);font-size:20px;">&#9873;</span>';
      } else {
        const best=argmax(q[i]);
        const maxV=q[i][best];
        let bg='var(--surface-2)';
        if(maxV>0.15) bg='var(--success-bg)';
        else if(maxV<-0.15) bg='var(--danger-bg)';
        style='background:'+bg+';';
        if(isStart && !isAgent) style='background:var(--start-bg);border:2px solid var(--start);';
        const color = maxV>0.15?'var(--success)':(maxV<-0.15?'var(--danger)':'var(--text-muted)');
        if(isAgent){
          const treadPhase=((frameTick*0.7)%6+6)%6;
          function treadTicks(yPos){
            let s='';
            for(let k=-2;k<4;k++){
              const tx=-9+k*6+treadPhase;
              if(tx>-8.5 && tx<8.5) s+='<rect x="'+tx.toFixed(1)+'" y="'+yPos+'" width="1.6" height="4" rx="0.5" fill="var(--bg)" opacity="0.5"/>';
            }
            return s;
          }
          const tank='<g transform="rotate('+facingDeg+')">'+
            '<rect x="-9" y="-7" width="18" height="4" rx="1.5" fill="var(--text-secondary)"/>'+treadTicks(-7)+
            '<rect x="-9" y="3" width="18" height="4" rx="1.5" fill="var(--text-secondary)"/>'+treadTicks(3)+
            '<rect x="-6" y="-4" width="13" height="8" rx="2" fill="var(--accent)"/>'+
            '<circle cx="1" cy="0" r="3.6" fill="var(--accent)" stroke="var(--bg)" stroke-width="0.7"/>'+
            '<line x1="1" y1="0" x2="13" y2="0" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"/></g>';
          inner='<span class="center agent-active" style="display:inline-flex;"><svg viewBox="-11 -9 24 18" width="22" height="17" style="overflow:visible;">'+tank+'</svg></span>';
        } else if(isStart){
          inner='<span style="color:var(--start);font-size:14px;">&#127968;</span>';
        } else {
          inner='<span style="color:'+color+';">'+(Math.abs(maxV)>0.15?ARROWS[best]:'·')+'</span>';
        }
      }
      html+='<div class="cell" style="'+style+'">'+inner+'</div>';
    }
    gridEl.innerHTML=html;

    if(comparePathsData){
      gridEl.style.position='relative';
      const overlay=document.createElement('div');
      overlay.style.cssText='position:absolute;inset:0;pointer-events:none;';
      overlay.innerHTML='<svg viewBox="0 0 100 100" preserveAspectRatio="none" style="width:100%;height:100%;">'+pathOverlaySvg()+'</svg>';
      gridEl.style.position='relative';
      gridEl.appendChild(overlay);
    }

    const rowLabels=[];
    for(let r=0;r<ROWS;r++) for(let c=0;c<COLS;c++) rowLabels.push('('+(r+1)+','+(c+1)+')');
    let tableHtml='<tr><th style="text-align:left;">cell</th><th>up</th><th>down</th><th>left</th><th>right</th></tr>';
    for(let i=0;i<ROWS*COLS;i++){
      if(CLIFF.has(i)) continue;
      let label=rowLabels[i];
      if(i===START) label+=' start';
      if(i===GOAL) label+=' goal';
      tableHtml+='<tr><td style="text-align:left;color:var(--text-secondary);">'+label+'</td>';
      for(let a=0;a<4;a++){
        const v=q[i][a];
        let bg='var(--surface)', col='var(--text-muted)';
        if(v>0.15){ bg='var(--success-bg)'; col='var(--success)'; }
        else if(v<-0.15){ bg='var(--danger-bg)'; col='var(--danger)'; }
        tableHtml+='<td style="background:'+bg+';color:'+col+';">'+v.toFixed(1)+'</td>';
      }
      tableHtml+='</tr>';
    }
    document.getElementById('cliff-qtable').innerHTML=tableHtml;
    document.getElementById('cliff-log').innerHTML=logHtml();
  }

  drawGammaChart();
  render();

  return { train, walkGreedy, comparePaths, resetAll, setAlgo, setParam, setSpeed, setReward, toggleLogDetail };
})();
