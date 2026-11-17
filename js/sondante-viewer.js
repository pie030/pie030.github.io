/* The viewer reads the same GLB included in the project. No external runtime. */
(() => {
  const panel = document.getElementById('viewer');
  const canvas = document.getElementById('model');
  const status = document.getElementById('viewer-status');
  const start = document.getElementById('open-model');
  const track = document.getElementById('cycle-range');
  const clock = document.getElementById('cycle-clock');
  const play = document.getElementById('play-cycle');
  let gl, program, items, nodes, channels, materials, roots, uniforms;
  let duration = 12;
  let angle = 31.5 * Math.PI / 180;
  let elevation = 18.5 * Math.PI / 180;
  let zoom = 1;
  let seconds = 3.60;
  let mode = 'material';
  let playing = false;
  let lastTime = 0;
  let redraw = false;
  let loaded = false;
  const pointers = new Map();
  const phases = [
    [0, 'Stowed'], [10/24, 'Deploying'], [84/24, 'Settling'],
    [91/24, 'Lowering'], [153/24, 'Sampling'], [173/24, 'Retrieving'],
    [229/24, 'Securing'], [240/24, 'Stowing'], [283/24, 'Stowed'],
  ];
  const sub = (a,b) => a.map((v,i) => v-b[i]);
  const dot = (a,b) => a.reduce((s,v,i) => s+v*b[i],0);
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const unit = a => a.map(v => v / Math.hypot(...a));
  const clamp = (value, a, b) => Math.min(b, Math.max(a,value));
  const mix = (a,b,t) => a+(b-a)*t;
  const identity = () => new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);

  function multiply(a,b) {
    const out = new Float32Array(16);
    for (let col=0; col<4; col++) {
      for (let row=0; row<4; row++) {
        out[col*4+row] =
          a[row]*b[col*4]+a[4+row]*b[col*4+1]+a[8+row]*b[col*4+2]+a[12+row]*b[col*4+3];
      }
    }
    return out;
  }
  function fromTRS(t,q,s) {
    const [x,y,z,w]=q;
    return new Float32Array([
      (1-2*(y*y+z*z))*s[0], 2*(x*y+z*w)*s[0], 2*(x*z-y*w)*s[0], 0,
      2*(x*y-z*w)*s[1], (1-2*(x*x+z*z))*s[1], 2*(y*z+x*w)*s[1], 0,
      2*(x*z+y*w)*s[2], 2*(y*z-x*w)*s[2], (1-2*(x*x+y*y))*s[2], 0,
      ...t,1,
    ]);
  }
  function lookAt(eye,target) {
    const z=unit(sub(eye,target)), x=unit(cross([0,1,0],z)), y=cross(z,x);
    return new Float32Array([
      x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
      -dot(x,eye),-dot(y,eye),-dot(z,eye),1,
    ]);
  }
  function projection(fovy,aspect,n,f) {
    const factor=1/Math.tan(fovy/2);
    return new Float32Array([factor/aspect,0,0,0, 0,factor,0,0, 0,0,(f+n)/(n-f),-1, 0,0,2*f*n/(n-f),0]);
  }

  const vertexSource = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 aPosition;
    layout(location=1) in vec3 aNormal;
    uniform mat4 uWorld;
    uniform mat4 uViewProjection;
    out vec3 normal;
    out vec3 pos;
    void main() {
      vec4 world = uWorld*vec4(aPosition,1);
      normal = mat3(transpose(inverse(uWorld)))*aNormal;
      pos = world.xyz;
      gl_Position = uViewProjection*world;
    }`;
  const fragmentSource = `#version 300 es
    precision highp float;
    in vec3 normal;
    in vec3 pos;
    uniform vec3 uColor;
    uniform vec3 uEmission;
    uniform vec3 uEye;
    uniform float uMetal;
    uniform float uRough;
    uniform int uStyle;
    out vec4 color;
    void main() {
      if(uStyle==2) {
        color=vec4(.75,.87,.74,1);
        return;
      }
      if(uStyle==3) {
        color=vec4(.105,.165,.150,1);
        return;
      }
      vec3 n=normalize(normal);
      vec3 v=normalize(uEye-pos);
      vec3 key=normalize(vec3(-2.7,4.5,5.5));
      vec3 fill=normalize(vec3(4.4,1.7,-3.4));
      vec3 base=uStyle==1?vec3(.51,.49,.42):uColor;
      float metal=uStyle==1?0.:uMetal;
      float hemi=.27+.23*(n.y*.5+.5);
      float shade=hemi+.72*max(dot(n,key),0.)+.36*max(dot(n,fill),0.);
      float p=mix(102.,14.,uRough);
      float kspec=pow(max(dot(n,normalize(v+key)),0.),p);
      float fspec=pow(max(dot(n,normalize(v+fill)),0.),p*.8);
      float edge=pow(1.-max(dot(n,v),0.),3.);
      vec3 spec=mix(vec3(.045),sqrt(base),metal*.65)*(kspec*.63+fspec*.35);
      vec3 rgb=base*shade*(1.-metal*.34)+spec+(vec3(.015,.024,.021)+base*.035)*edge;
      if(uStyle==0) rgb+=uEmission*.56;
      color=vec4(pow(clamp(rgb,0.,1.),vec3(1./2.2)),1);
    }`;

  function shader(kind, source) {
    const s=gl.createShader(kind);
    gl.shaderSource(s,source);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(s));
    return s;
  }
  function initGL() {
    gl=canvas.getContext('webgl2',{antialias:true,alpha:true,premultipliedAlpha:false});
    if(!gl) throw Error('WebGL2 unavailable');
    program=gl.createProgram();
    gl.attachShader(program,shader(gl.VERTEX_SHADER,vertexSource));
    gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragmentSource));
    gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    uniforms=Object.fromEntries(['World','ViewProjection','Color','Emission','Eye','Metal','Rough','Style']
      .map(name=>[name,gl.getUniformLocation(program,'u'+name)]));
    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0,0,0,0);
  }

  function loadGlb(buffer) {
    const dv=new DataView(buffer);
    if (dv.getUint32(0,true)!==0x46546c67 || dv.getUint32(4,true)!==2) throw Error('Unsupported GLB');
    const jsonLength=dv.getUint32(12,true);
    const data=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,jsonLength)));
    const bin=28+jsonLength;
    const components={SCALAR:1,VEC2:2,VEC3:3,VEC4:4};
    const types={5121:Uint8Array,5123:Uint16Array,5125:Uint32Array,5126:Float32Array};
    const views=new Map();
    function accessor(index) {
      if (views.has(index)) return views.get(index);
      const a=data.accessors[index], view=data.bufferViews[a.bufferView];
      const Type=types[a.componentType], width=components[a.type];
      const offset=bin+(view.byteOffset??0)+(a.byteOffset??0);
      const packed=Type.BYTES_PER_ELEMENT*width;
      if ((view.byteStride??packed)!==packed) throw Error('Unsupported accessor stride');
      const values=new Type(buffer,offset,a.count*width);
      views.set(index,values);
      return values;
    }
    function attribute(loc,index) {
      const buf=gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER,buf);
      gl.bufferData(gl.ARRAY_BUFFER,accessor(index),gl.STATIC_DRAW);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc,3,gl.FLOAT,false,0,0);
    }
    function indexBuffer(values) {
      const buf=gl.createBuffer();
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,buf);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,values,gl.STATIC_DRAW);
      return buf;
    }
    function primitive(p) {
      const vao=gl.createVertexArray();
      gl.bindVertexArray(vao);
      attribute(0,p.attributes.POSITION);
      attribute(1,p.attributes.NORMAL);
      const idx=accessor(p.indices);
      const Type=idx.constructor;
      const type=data.accessors[p.indices].componentType;
      const elements=indexBuffer(idx);
      const seen=new Set();
      const pairs=[];
      for(let i=0; i<idx.length; i+=3) {
        const tri=[idx[i],idx[i+1],idx[i+2]];
        for(let j=0; j<3; j++) {
          const a=tri[j], b=tri[(j+1)%3];
          const key=a<b?a+'/'+b:b+'/'+a;
          if(!seen.has(key)) {
            seen.add(key);
            pairs.push(a,b);
          }
        }
      }
      const edges=indexBuffer(new Type(pairs));
      gl.bindVertexArray(null);
      return {vao,elements,edges,count:idx.length,edgeCount:pairs.length,type,mat:p.material};
    }
    nodes=data.nodes.map(n=>({
      ...n, translation:n.translation??[0,0,0], rotation:n.rotation??[0,0,0,1], scale:n.scale??[1,1,1],
    }));
    items=data.meshes.map(m=>m.primitives.map(primitive));
    materials=data.materials;
    roots=data.scenes[data.scene??0].nodes;
    channels=data.animations.flatMap(a=>a.channels.map(ch=>{
      const sampler=a.samplers[ch.sampler];
      const input=accessor(sampler.input);
      const output=accessor(sampler.output);
      return {target:ch.target,input,output,width:output.length/input.length};
    }));
    duration=Math.max(...channels.map(c=>c.input[c.input.length-1]));
    track.max=duration.toFixed(3);
  }

  function channelValue(channel,t) {
    const {input,output,width,target}=channel;
    let lower=0, upper=input.length-1;
    while(upper-lower>1) {
      const mid=(upper+lower)>>1;
      if(input[mid]<=t) lower=mid;
      else upper=mid;
    }
    const a=Array.from(output.subarray(lower*width,(lower+1)*width));
    const b=Array.from(output.subarray(upper*width,(upper+1)*width));
    const w=clamp((t-input[lower])/(input[upper]-input[lower]||1),0,1);
    if(target.path!=='rotation') return a.map((v,i)=>mix(v,b[i],w));
    const sign=dot(a,b)<0?-1:1;
    const angleCos=clamp(dot(a,b)*sign,-1,1);
    if(angleCos>.9995) return unit(a.map((v,i)=>mix(v,sign*b[i],w)));
    const theta=Math.acos(angleCos);
    const n=Math.sin(theta);
    return a.map((v,i)=>(v*Math.sin((1-w)*theta)+sign*b[i]*Math.sin(w*theta))/n);
  }
  function draw() {
    const dpr=Math.min(devicePixelRatio,1.65);
    const w=Math.max(1,Math.round(canvas.clientWidth*dpr));
    const h=Math.max(1,Math.round(canvas.clientHeight*dpr));
    if (canvas.width!==w||canvas.height!==h) {
      canvas.width=w;
      canvas.height=h;
    }
    gl.viewport(0,0,w,h);
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const aspect=w/h;
    const distance=(aspect<1.15?7.1*(1.15/aspect)**.8:7.1)/zoom;
    const target=[.52,.88,0];
    const eye=[
      target[0]+distance*Math.sin(angle)*Math.cos(elevation),
      target[1]+distance*Math.sin(elevation),
      target[2]+distance*Math.cos(angle)*Math.cos(elevation),
    ];
    gl.uniform3fv(uniforms.Eye,eye);
    gl.uniformMatrix4fv(uniforms.ViewProjection,false,multiply(projection(.60,aspect,.06,55),lookAt(eye,target)));
    for(const channel of channels) {
      nodes[channel.target.node][channel.target.path]=channelValue(channel,seconds);
    }
    const queue=[];
    function visit(i,parent) {
      const n=nodes[i];
      const world=multiply(parent,n.matrix??fromTRS(n.translation,n.rotation,n.scale));
      if(n.mesh!==undefined) queue.push([world,items[n.mesh]]);
      for(const child of n.children??[]) visit(child,world);
    }
    for (const root of roots) visit(root,identity());
    function pass(style) {
      gl.uniform1i(uniforms.Style,style);
      for(const [world,meshes] of queue) {
        gl.uniformMatrix4fv(uniforms.World,false,world);
        for (const p of meshes) {
          const m=materials[p.mat]??{};
          const pbr=m.pbrMetallicRoughness??{};
          gl.uniform3fv(uniforms.Color,(pbr.baseColorFactor??[.5,.5,.5]).slice(0,3));
          gl.uniform3fv(uniforms.Emission,m.emissiveFactor??[0,0,0]);
          gl.uniform1f(uniforms.Metal,pbr.metallicFactor??0);
          gl.uniform1f(uniforms.Rough,pbr.roughnessFactor??.5);
          gl.bindVertexArray(p.vao);
          gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,style===2?p.edges:p.elements);
          gl.drawElements(style===2?gl.LINES:gl.TRIANGLES,style===2?p.edgeCount:p.count,p.type,0);
        }
      }
    }
    if(mode==='wire') {
      gl.enable(gl.POLYGON_OFFSET_FILL);
      gl.polygonOffset(1,1);
      pass(3);
      gl.disable(gl.POLYGON_OFFSET_FILL);
      pass(2);
    } else {
      pass(mode==='clay'?1:0);
    }
  }
  const phaseAt=t=>phases.reduce((name,[from,label])=>t>=from?label:name,'Stowed');
  function updateLabel() {
    const label=phaseAt(seconds);
    track.value=seconds.toFixed(3);
    track.setAttribute('aria-valuetext',seconds.toFixed(2)+' seconds, '+label);
    clock.textContent=seconds.toFixed(2)+' / '+duration.toFixed(2)+' s';
    document.getElementById('phase-label').textContent=label;
    for(const button of document.querySelectorAll('[data-stage]')) {
      const active=button.dataset.stage===label;
      button.setAttribute('aria-pressed',String(active));
    }
  }
  function rerender() {
    if(!loaded||redraw) return;
    redraw=true;
    requestAnimationFrame(frame);
  }
  function frame(now) {
    redraw=false;
    if(playing) {
      if(lastTime) {
        seconds=(seconds+Math.min(.12,(now-lastTime)/1000))%duration;
        updateLabel();
      }
      lastTime=now;
    }
    draw();
    if(playing) rerender();
  }
  function setPlaying(on) {
    playing=on;
    lastTime=0;
    play.textContent=on?'Pause cycle':'Play cycle';
    play.setAttribute('aria-pressed',String(on));
    rerender();
  }
  function seek(t) {
    setPlaying(false);
    seconds=clamp(t,0,duration);
    updateLabel();
    rerender();
  }
  function setZoom(value) {
    zoom=clamp(value,.70,2.7);
    rerender();
  }
  function setCamera(a,e) {
    angle=a;
    elevation=clamp(e,-.79,1.42);
    rerender();
  }
  function fallback(message) {
    loaded=false;
    setPlaying(false);
    panel.dataset.ready='fallback';
    status.textContent=message;
    start.hidden=true;
    document.getElementById('controls').hidden=true;
  }
  start.addEventListener('click',()=>{
    start.disabled=true;
    status.textContent='Loading the model…';
    requestAnimationFrame(async()=>{
      try {
        initGL();
        const embedded=document.getElementById('embedded-glb');
        let buffer;
        if (embedded.dataset.src) {
          const response=await fetch(embedded.dataset.src);
          if(!response.ok) throw Error('Model download failed: '+response.status);
          buffer=await response.arrayBuffer();
        } else {
          const decoded=atob(embedded.textContent.trim());
          const bytes=new Uint8Array(decoded.length);
          for(let i=0;i<bytes.length;i++) bytes[i]=decoded.charCodeAt(i);
          buffer=bytes.buffer;
        }
        loadGlb(buffer);
        loaded=true;
        panel.dataset.ready='true';
        document.getElementById('controls').hidden=false;
        start.hidden=true;
        status.textContent='Drag to orbit. Pinch or use the zoom buttons.';
        updateLabel();
        canvas.focus({preventScroll:true});
        draw();
      } catch (e) {
        console.warn('Sondante 3D viewer:',e.message);
        fallback(e.message==='WebGL2 unavailable'
          ?'Live 3D needs WebGL 2. The render gallery remains available.'
          :'The live model could not open. The render gallery remains available.');
      }
    });
  });
  canvas.addEventListener('webglcontextlost',event=>{
    event.preventDefault();
    fallback('The graphics context closed. Reload to reopen the live model.');
  });
  play.addEventListener('click',()=>setPlaying(!playing));
  track.addEventListener('input',()=>seek(Number(track.value)));
  for (const button of document.querySelectorAll('[data-seek]')) {
    button.addEventListener('click',()=>seek(Number(button.dataset.seek)));
  }
  for(const button of document.querySelectorAll('[data-mode]')) {
    button.addEventListener('click',()=>{
      mode=button.dataset.mode;
      for(const other of document.querySelectorAll('[data-mode]')) {
        other.setAttribute('aria-pressed',String(other===button));
      }
      rerender();
    });
  }
  for(const button of document.querySelectorAll('[data-camera]')) {
    button.addEventListener('click',()=>{
      const [a,e]=button.dataset.camera.split(',').map(Number);
      zoom=1;
      setCamera(a*Math.PI/180,e*Math.PI/180);
    });
  }
  for(const button of document.querySelectorAll('[data-zoom]')) {
    button.addEventListener('click',()=>setZoom(zoom*Number(button.dataset.zoom)));
  }
  canvas.addEventListener('wheel',event=>{
    if(!loaded||!event.ctrlKey) return;
    event.preventDefault();
    setZoom(zoom*Math.exp(-event.deltaY*.003));
  },{passive:false});
  canvas.addEventListener('pointerdown',event=>{
    if(!loaded||event.button!==0) return;
    pointers.set(event.pointerId,[event.clientX,event.clientY]);
    canvas.setPointerCapture(event.pointerId);
  });
  const separation=()=>Math.hypot(...sub(...pointers.values()));
  canvas.addEventListener('pointermove',event=>{
    const old=pointers.get(event.pointerId);
    if(!old) return;
    const pinch=pointers.size===2?separation():0;
    pointers.set(event.pointerId,[event.clientX,event.clientY]);
    if (pinch>0) {
      setZoom(zoom*separation()/pinch);
    } else if (pointers.size===1) {
      setCamera(angle-(event.clientX-old[0])*.009,elevation+(event.clientY-old[1])*.009);
    }
  });
  for(const name of ['pointerup','pointercancel','lostpointercapture']) {
    canvas.addEventListener(name,event=>pointers.delete(event.pointerId));
  }
  canvas.addEventListener('keydown',event=>{
    if(!loaded) return;
    const actions={
      ArrowLeft:()=>setCamera(angle+.12,elevation),
      ArrowRight:()=>setCamera(angle-.12,elevation),
      ArrowUp:()=>setCamera(angle,elevation+.12),
      ArrowDown:()=>setCamera(angle,elevation-.12),
      '+':()=>setZoom(zoom*1.13), '=':()=>setZoom(zoom*1.13), '-':()=>setZoom(zoom/1.13),
      ' ':()=>setPlaying(!playing),
    };
    if(actions[event.key]) {
      event.preventDefault();
      actions[event.key]();
    }
  });
  new ResizeObserver(rerender).observe(canvas);
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden&&playing) setPlaying(false);
  });
  if('IntersectionObserver' in window) {
    new IntersectionObserver(([entry])=>{
      if(!entry.isIntersecting&&playing) setPlaying(false);
    },{threshold:.04}).observe(panel);
  }
})();
