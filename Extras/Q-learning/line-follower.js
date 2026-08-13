const Line = (function(){
  const X0=40, X1=640, BASEY=170;
  const N_POINTS=6;
  const controlX=[];
  for(let i=0;i<N_POINTS;i++) controlX.push(X0 + i*(X1-X0)/(N_POINTS-1));
  // default shape matches the original sine curve, sampled at each control point
  const defaultAMP=55, defaultFREQ=1/90;
  function defaultY(x){ return BASEY + defaultAMP*Math.sin((x-X0)*defaultFREQ); }
  let controlY = controlX.map(defaultY);

  const Y_MIN=90, Y_MAX=230;
  let editMode=false;
  let dragIndex=-1;

  function segAt(x){
    const dx=(X1-X0)/(N_POINTS-1);
    let i=Math.floor((x-X0)/dx);
    i=Math.max(0,Math.min(N_POINTS-2,i));
    return {i, dx, t:(x-(X0+i*dx))/dx};
  }
  function tangentAt(i){
    if(i<=0) return controlY[1]-controlY[0];
    if(i>=N_POINTS-1) return controlY[N_POINTS-1]-controlY[N_POINTS-2];
    return (controlY[i+1]-controlY[i-1])/2;
  }
  function centerlineY(x){
    const {i,t}=segAt(x);
    const y0=controlY[i], y1=controlY[i+1];
    const m0=tangentAt(i), m1=tangentAt(i+1);
    const t2=t*t, t3=t2*t;
    const h00=2*t3-3*t2+1, h10=t3-2*t2+t, h01=-2*t3+3*t2, h11=t3-t2;
    return h00*y0 + h10*m0 + h01*y1 + h11*m1;
  }
  function centerlineSlope(x){
    const {i,dx,t}=segAt(x);
    const y0=controlY[i], y1=controlY[i+1];
    const m0=tangentAt(i), m1=tangentAt(i+1);
    const t2=t*t;
    const dh00=6*t2-6*t, dh10=3*t2-4*t+1, dh01=-6*t2+6*t, dh11=3*t2-2*t;
    return (dh00*y0+dh10*m0+dh01*y1+dh11*m1)/dx;
  }
  function bezierSegments(offset){
    const dx=(X1-X0)/(N_POINTS-1);
    let d='M '+controlX[0].toFixed(1)+' '+(controlY[0]+offset).toFixed(1)+' ';
    for(let i=0;i<N_POINTS-1;i++){
      const y0=controlY[i]+offset, y1=controlY[i+1]+offset;
      const m0=tangentAt(i), m1=tangentAt(i+1);
      const c1x=controlX[i]+dx/3, c1y=y0+m0/3;
      const c2x=controlX[i+1]-dx/3, c2y=y1-m1/3;
      d+='C '+c1x.toFixed(1)+' '+c1y.toFixed(1)+', '+c2x.toFixed(1)+' '+c2y.toFixed(1)+', '+controlX[i+1].toFixed(1)+' '+y1.toFixed(1)+' ';
    }
    return d;
  }
  function resetTrackShape(){
    controlY = controlX.map(defaultY);
    msg('Track reshaped back to the default curve.');
    resetRobot();
    render();
  }
  function toggleEditMode(){
    editMode=!editMode;
    document.getElementById('line-edit-btn').classList.toggle('active', editMode);
    document.getElementById('line-edit-hint').style.display = editMode ? 'block' : 'none';
    render();
  }
  function svgPoint(clientX,clientY){
    const svgEl=document.getElementById('line-trackSvg');
    const pt=svgEl.createSVGPoint();
    pt.x=clientX; pt.y=clientY;
    const ctm=svgEl.getScreenCTM().inverse();
    return pt.matrixTransform(ctm);
  }
  function startDrag(i, evt){
    if(!editMode) return;
    dragIndex=i;
    evt.preventDefault();
  }
  function onPointerMove(evt){
    if(dragIndex<0) return;
    const touch = evt.touches ? evt.touches[0] : evt;
    const p=svgPoint(touch.clientX, touch.clientY);
    controlY[dragIndex]=Math.max(Y_MIN, Math.min(Y_MAX, p.y));
    render();
  }
  function onPointerUp(){ dragIndex=-1; }
  document.addEventListener('mousemove', onPointerMove);
  document.addEventListener('mouseup', onPointerUp);
  document.addEventListener('touchmove', onPointerMove, {passive:true});
  document.addEventListener('touchend', onPointerUp);

  const BAND_W=80/3;
  const OFFTRACK=1.5*BAND_W;
  const COLORS=['red','blue','green'];
  function colorIdx(c){ return COLORS.indexOf(c); }
  function classify(offset){
    if(Math.abs(offset)>OFFTRACK) return 'off';
    if(offset<-BAND_W/2) return 'red';
    if(offset>BAND_W/2) return 'green';
    return 'blue';
  }

  let ALPHA=0.5, GAMMA=0.9, EPS=0.2;
  const TURN=0.16, STEP_DIST=10, MAXSTEPS=220;
  let blueReward=1, sideReward=0.1, offPenalty=-5;
  const FINISH_BONUS=20;
  let speedLevel=6;
  let isAnimating=false;
  let episodesTrained=0;
  let logLines=[];
  let logIdCounter=0;
  let expandedLogId=null;
  let epStepCount=0;
  let epExploreCount=0;
  let Q=Array.from({length:3},()=>[0,0,0]);

  let rx,ry,rtheta,trail=[];
  function resetRobot(){
    rx=X0; ry=centerlineY(X0); rtheta=Math.atan(centerlineSlope(X0)); trail=[];
  }
  resetRobot();

  const ACT=['turn left','straight','turn right'];
  function argmax(a){ let bi=0; for(let i=1;i<a.length;i++){ if(a[i]>a[bi]) bi=i; } return bi; }
  function stateIdx(cur){ return colorIdx(cur); }
  function effEps(){ return EPS*Math.max(0.05, 1-episodesTrained/2000); }
  function effAlpha(){ return ALPHA*Math.max(0.15, 1-episodesTrained/3000); }

  function doMove(action){
    rtheta += action===0 ? -TURN : action===2 ? TURN : 0;
    rx += STEP_DIST*Math.cos(rtheta);
    ry += STEP_DIST*Math.sin(rtheta);
    trail.push({x:rx,y:ry});
    if(trail.length>50) trail.shift();
    const offset = ry-centerlineY(rx);
    const color = classify(offset);
    let reward, done=false;
    if(color==='off'){ reward=offPenalty; done=true; }
    else if(color==='blue'){ reward=blueReward; }
    else { reward=sideReward; }
    if(color!=='off' && rx>=X1){ reward+=FINISH_BONUS; done=true; }
    return {color, reward, done};
  }

  function setParam(name,val,outId){
    const v=parseFloat(val);
    if(name==='ALPHA') ALPHA=v;
    if(name==='GAMMA'){ GAMMA=v; drawGammaChart(); }
    if(name==='EPS') EPS=v;
    document.getElementById(outId).textContent=v.toFixed(2);
  }
  function setSpeed(v){ speedLevel=parseInt(v); document.getElementById('line-speed-out').textContent=speedLevel; }
  function getDelay(){ return 260-speedLevel*22; }
  function setReward(name,val){
    const v=parseFloat(val);
    if(name==='blueReward') blueReward=v;
    if(name==='sideReward') sideReward=v;
    if(name==='offPenalty') offPenalty=v;
  }

  function resetQ(){
    if(isAnimating){ msg('Hang on for the current episode to finish.'); return; }
    Q=Array.from({length:3},()=>[0,0,0]);
    episodesTrained=0;
    logLines=[];
    resetRobot();
    msg('Q-table reset.');
    render();
  }

  function trainBulk(n){
    if(isAnimating){ msg('Hang on for the current episode to finish.'); return; }
    let successes=0;
    epStepCount=0;
    epExploreCount=0;
    for(let e=0;e<n;e++){
      resetRobot();
      let curColor='blue', t=0, done=false;
      while(!done && t<MAXSTEPS){
        const s=stateIdx(curColor);
        const explore = Math.random()<effEps();
        const a = explore ? Math.floor(Math.random()*3) : argmax(Q[s]);
        epStepCount++;
        if(explore) epExploreCount++;
        const {color,reward,done:d}=doMove(a);
        const nextColor=color==='off'?curColor:color;
        const nextS=stateIdx(nextColor);
        const nextVals=Q[nextS].slice();
        const maxNext=Math.max(...nextVals);
        const before=Q[s][a];
        Q[s][a]+=effAlpha()*(reward+GAMMA*maxNext-Q[s][a]);
        const after=Q[s][a];
        logLines.unshift({id:logIdCounter++, color:curColor, nextColor, action:ACT[a], actionIdx:a, reward, alpha:effAlpha(), gamma:GAMMA, before, after, nextVals, maxNext, explore});
        curColor=nextColor;
        done=d; t++;
        if(d && reward>=FINISH_BONUS) successes++;
      }
      episodesTrained++;
    }
    logLines=logLines.slice(0,8);
    resetRobot();
    msg('Trained '+episodesTrained+' total episodes. '+successes+' of the last '+n+' reached the finish line.');
    render();
  }

  function train(){
    if(isAnimating){ msg('Hang on for the current episode to finish.'); return; }
    const el=document.getElementById('line-episode-input');
    const n=parseInt(el.value,10)||0;
    if(n<=0){ msg('Enter a number of episodes, then click Train.'); return; }
    if(n===1){ runEpisodeAnimated(); }
    else { trainBulk(n); }
  }

  function runEpisodeAnimated(){
    if(isAnimating){ msg('Hang on for the current episode to finish.'); return; }
    isAnimating=true;
    logLines=[];
    resetRobot();
    let curColor='blue', t=0;
    epStepCount=0;
    epExploreCount=0;
    render();

    function step(){
      if(t>=MAXSTEPS){
        isAnimating=false; episodesTrained++;
        msg('Ran out of steps. Episodes trained: '+episodesTrained+'.');
        render();
        return;
      }
      setTimeout(()=>{
        const s=stateIdx(curColor);
        const explore = Math.random()<effEps();
        const a = explore ? Math.floor(Math.random()*3) : argmax(Q[s]);
        epStepCount++;
        if(explore) epExploreCount++;
        const {color,reward,done}=doMove(a);
        const nextColor = color==='off'?curColor:color;
        const nextS=stateIdx(nextColor);
        const before=Q[s][a];
        const nextVals=Q[nextS].slice();
        const maxNext=Math.max(...nextVals);
        Q[s][a]+=effAlpha()*(reward+GAMMA*maxNext-Q[s][a]);
        const after=Q[s][a];
        logLines.unshift({id:logIdCounter++, color:curColor, nextColor, action:ACT[a], actionIdx:a, reward, alpha:effAlpha(), gamma:GAMMA, before, after, nextVals, maxNext, explore});
        logLines=logLines.slice(0,8);
        curColor=nextColor; t++;
        render();
        if(done){
          isAnimating=false; episodesTrained++;
          msg(color==='off' ? 'Fell off the track after '+t+' steps.' : 'Reached the finish line in '+t+' steps!');
          render();
          return;
        }
        step();
      }, getDelay());
    }
    step();
  }

  function testPolicy(){
    if(isAnimating){ msg('Hang on for the current run to finish.'); return; }
    isAnimating=true;
    logLines=['Testing learned policy — no exploration, no learning.'];
    resetRobot();
    let curColor='blue', t=0;
    render();

    function step(){
      if(t>=MAXSTEPS){
        isAnimating=false;
        msg('Test ran out of steps without reaching the finish line.');
        render();
        return;
      }
      setTimeout(()=>{
        const s=stateIdx(curColor);
        const a = argmax(Q[s]);
        const {color,reward,done}=doMove(a);
        const nextColor = color==='off'?curColor:color;
        logLines.unshift(curColor+'  '+ACT[a]+'  (greedy, no update)');
        logLines=logLines.slice(0,8);
        curColor=nextColor; t++;
        render();
        if(done){
          isAnimating=false;
          msg(color==='off' ? 'Test failed — fell off the track after '+t+' steps.' : 'Test succeeded — reached the finish line in '+t+' steps.');
          render();
          return;
        }
        step();
      }, getDelay());
    }
    step();
  }

  function msg(t){ document.getElementById('line-msg').textContent=t; }

  function toggleLogDetail(id){
    expandedLogId = (expandedLogId===id) ? null : id;
    render();
  }

  function nextValsBarChart(nextVals, maxNext){
    const w=200,h=64,baseline=34;
    const maxAbs=Math.max(1, ...nextVals.map(v=>Math.abs(v)));
    const scale=24/maxAbs;
    const labels=['L','S','R'];
    const barW=40, gap=20;
    let bars='';
    for(let i=0;i<3;i++){
      const v=nextVals[i];
      const bh=Math.max(1,Math.abs(v)*scale);
      const x=20+i*(barW+gap);
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

  function drawGammaChart(){
    const el=document.getElementById('line-gamma-chart');
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
      const summary=modeTag+'  '+entry.color+' \u2192 '+entry.action+
        '  reward '+sign+entry.reward.toFixed(2)+'  Q: '+entry.before.toFixed(2)+' \u2192 '+entry.after.toFixed(2);
      let detail='';
      if(expanded){
        const gm=entry.gamma*entry.maxNext;
        const target=entry.reward+gm;
        const tdError=target-entry.before;
        const alphaErr=entry.alpha*tdError;
        const rewardSpan='<span style="color:var(--success);font-weight:600;">'+entry.reward.toFixed(3)+'</span>';
        const futureSpan='<span style="color:var(--accent);font-weight:600;">'+gm.toFixed(3)+'</span>';
        const gmFormula='<span style="color:var(--accent);font-weight:600;">'+entry.gamma.toFixed(2)+' &times; '+entry.maxNext.toFixed(3)+'</span>';
        const modeExplain = entry.explore
          ? '<span style="color:var(--goal);">This action was chosen at random (exploration), not from the table.</span>'
          : '<span style="color:var(--accent);">This action was the table\u2019s current best guess (exploitation).</span>';
        detail='<div style="margin:4px 0 8px 0;padding:10px 12px;background:var(--surface-2);border-left:2px solid var(--accent);border-radius:4px;font-size:10.5px;line-height:1.8;">'+
          modeExplain+'<br>'+
          'Sensor was <strong>'+entry.color+'</strong>, took <strong>'+entry.action+'</strong>, sensor became <strong>'+entry.nextColor+'</strong><br>'+
          'Q(s,a) before &nbsp;= '+entry.before.toFixed(3)+'<br>'+
          '<span style="color:var(--success);">reward (real, this step)</span> = '+rewardSpan+'<br>'+
          'next-state Q-values (for sensor='+entry.nextColor+') — max highlighted is the borrowed estimate:'+
          nextValsBarChart(entry.nextVals, entry.maxNext)+
          '<span style="color:var(--accent);">&gamma; &times; max(Q(s&prime;)) (estimated future)</span> = '+gmFormula+' = '+futureSpan+'<br>'+
          'target = '+rewardSpan+' + '+futureSpan+' = '+target.toFixed(3)+'<br>'+
          'TD error = target &minus; before = '+target.toFixed(3)+' &minus; '+entry.before.toFixed(3)+' = '+tdError.toFixed(3)+'<br>'+
          '&alpha; &times; TD error = '+entry.alpha.toFixed(2)+' &times; '+tdError.toFixed(3)+' = '+alphaErr.toFixed(3)+'<br>'+
          'Q(s,a) after = before + &alpha;&times;error = '+entry.before.toFixed(3)+' + '+alphaErr.toFixed(3)+' = <strong>'+entry.after.toFixed(3)+'</strong>'+
          '</div>';
      }
      return '<div style="cursor:pointer;" onclick="Line.toggleLogDetail('+entry.id+')">'+summary+
        ' <span style="color:var(--text-muted);font-size:9px;">'+(expanded?'&#9650; hide math':'&#9660; show math')+'</span></div>'+detail;
    }).join('');
  }

  function render(){
    const statsEl=document.getElementById('line-stats');
    const exploreRate = epStepCount>0 ? Math.round(epExploreCount/epStepCount*100) : null;
    const exploreStat = exploreRate!==null
      ? '<span>Exploring: '+epExploreCount+'/'+epStepCount+' steps this run ('+exploreRate+'%, target '+Math.round(effEps()*100)+'%)</span>'
      : '';
    statsEl.innerHTML =
      '<span>Episodes trained: '+episodesTrained+'</span>'+
      '<span>Progress: '+Math.max(0,Math.min(100,Math.round((rx-X0)/(X1-X0)*100)))+'%</span>'+
      '<span>Effective &epsilon;: '+effEps().toFixed(2)+'</span>'+
      '<span>Effective &alpha;: '+effAlpha().toFixed(2)+'</span>'+
      exploreStat;

    const offset=ry-centerlineY(rx);
    const curColor=classify(offset);
    const badgeMap={
      red:['#fcebeb','#a32d2d','Red'],
      blue:['#e6f1fb','#185fa5','Blue'],
      green:['#eaf3de','#3b6d11','Green'],
      off:['var(--surface-2)','var(--text-muted)','Off track']
    };
    const [bg,fg,label]=badgeMap[curColor];
    const badge=document.getElementById('line-sensorBadge');
    badge.style.background=bg; badge.style.color=fg; badge.textContent=label;

    let trailSvg='';
    for(const p of trail){
      trailSvg+='<circle cx="'+p.x.toFixed(1)+'" cy="'+p.y.toFixed(1)+'" r="1.6" fill="var(--text-muted)" opacity="0.35"/>';
    }

    const deg=(rtheta*180/Math.PI).toFixed(1);
    const treadPhase=((rx*0.8)%6+6)%6;
    function treadTicks(yPos){
      let s='';
      for(let i=-2;i<4;i++){
        const tx=-9+i*6+treadPhase;
        if(tx>-8.5 && tx<8.5){
          s+='<rect x="'+tx.toFixed(1)+'" y="'+yPos+'" width="1.6" height="4" rx="0.5" fill="var(--bg)" opacity="0.5"/>';
        }
      }
      return s;
    }
    const robotSvg='<g transform="translate('+rx.toFixed(1)+','+ry.toFixed(1)+') rotate('+deg+')">'+
      '<rect x="-9" y="-7" width="18" height="4" rx="1.5" fill="var(--text-secondary)"/>'+
      treadTicks(-7)+
      '<rect x="-9" y="3" width="18" height="4" rx="1.5" fill="var(--text-secondary)"/>'+
      treadTicks(3)+
      '<rect x="-6" y="-4" width="13" height="8" rx="2" fill="var(--accent)"/>'+
      '<circle cx="1" cy="0" r="3.6" fill="var(--accent)" stroke="var(--bg)" stroke-width="0.7"/>'+
      '<line x1="1" y1="0" x2="13" y2="0" stroke="var(--accent)" stroke-width="2" stroke-linecap="round"/>'+
      '</g>';

    const startY=centerlineY(X0), endY=centerlineY(X1);
    const markers=
      '<line x1="'+X0+'" y1="'+(startY-OFFTRACK-14)+'" x2="'+X0+'" y2="'+(startY+OFFTRACK+14)+'" stroke="var(--text-muted)" stroke-dasharray="4 4" stroke-width="1"/>'+
      '<line x1="'+X1+'" y1="'+(endY-OFFTRACK-14)+'" x2="'+X1+'" y2="'+(endY+OFFTRACK+14)+'" stroke="var(--text-muted)" stroke-dasharray="4 4" stroke-width="1"/>';

    let handlesSvg='';
    if(editMode){
      for(let i=0;i<N_POINTS;i++){
        handlesSvg+='<line x1="'+controlX[i]+'" y1="'+Y_MIN+'" x2="'+controlX[i]+'" y2="'+Y_MAX+'" stroke="var(--text-muted)" stroke-dasharray="2 3" stroke-width="1" opacity="0.4"/>'+
          '<circle cx="'+controlX[i]+'" cy="'+controlY[i]+'" r="7" fill="var(--bg)" stroke="var(--accent)" stroke-width="2" style="cursor:ns-resize" onmousedown="Line.startDrag('+i+',event)" ontouchstart="Line.startDrag('+i+',event)"/>';
      }
    }

    document.getElementById('line-trackSvg').innerHTML =
      '<path d="'+bezierSegments(-BAND_W)+'" stroke="#d64545" stroke-width="'+BAND_W+'" fill="none" stroke-linecap="round"/>'+
      '<path d="'+bezierSegments(BAND_W)+'" stroke="#4caf50" stroke-width="'+BAND_W+'" fill="none" stroke-linecap="round"/>'+
      '<path d="'+bezierSegments(0)+'" stroke="#3b82d8" stroke-width="'+BAND_W+'" fill="none" stroke-linecap="round"/>'+
      markers + trailSvg + (editMode ? '' : robotSvg) + handlesSvg;

    const highlightEntry = logLines.find(e=>typeof e!=='string' && e.id===expandedLogId);
    const fromIdx = highlightEntry ? colorIdx(highlightEntry.color) : -1;
    const toIdx = highlightEntry ? colorIdx(highlightEntry.nextColor) : -1;
    const fromAction = highlightEntry ? highlightEntry.actionIdx : -1;
    const toAction = highlightEntry ? argmax(highlightEntry.nextVals) : -1;

    const rowLabels=['Red','Blue','Green'];
    let tableHtml='<tr><th style="text-align:left;">sensor color</th><th>turn left</th><th>straight</th><th>turn right</th></tr>';
    for(let s=0;s<3;s++){
      let rowStyle='';
      if(s===fromIdx) rowStyle='border-left:3px solid var(--success);';
      else if(s===toIdx) rowStyle='border-left:3px solid var(--accent);';
      tableHtml+='<tr style="'+rowStyle+'"><td style="text-align:left;color:var(--text-secondary);">'+rowLabels[s]+
        (s===fromIdx?' <span style="font-size:9px;color:var(--success);">FROM</span>':'')+
        (s===toIdx?' <span style="font-size:9px;color:var(--accent);">TO</span>':'')+'</td>';
      for(let a=0;a<3;a++){
        const v=Q[s][a];
        let bg2='var(--surface)', col='var(--text-muted)';
        if(v>0.15){ bg2='var(--success-bg)'; col='var(--success)'; }
        else if(v<-0.15){ bg2='var(--danger-bg)'; col='var(--danger)'; }
        let cellStyle='background:'+bg2+';color:'+col+';';
        if(s===fromIdx && a===fromAction) cellStyle+='outline:2px solid var(--success);outline-offset:-2px;';
        if(s===toIdx && a===toAction) cellStyle+='outline:2px solid var(--accent);outline-offset:-2px;';
        tableHtml+='<td style="'+cellStyle+'">'+v.toFixed(2)+'</td>';
      }
      tableHtml+='</tr>';
    }
    document.getElementById('line-qtable').innerHTML=tableHtml;

    document.getElementById('line-log').innerHTML=logHtml();
  }

  drawGammaChart();
  render();

  return { train, testPolicy, resetQ, setParam, setSpeed, setReward, toggleEditMode, resetTrackShape, startDrag, toggleLogDetail };
})();
