// 用 CDP 真机验证「切换后图上的点位会不会变」——只校验 HTML 结构是不够的，
// 之前的问题恰恰是页面上点得动、图上不动。
//
// 用法：node check_page_marks.mjs
// 会依次点「全部」「跨阵位对照=2」「机位 cover_1」，每步打印可见圆点/打灰数量并截图到
// render/_chk_*.png。改完 gen_fp_page.py 的叠加层逻辑后必跑一遍。
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PAGE = 'F:\\Codex\\Nikke\\Nikke_Skills\\地图充能计算\\H35沼泽丛林玩家视角充能点.html';
const OUT = 'F:\\Codex\\Nikke\\Nikke_Skills\\地图充能计算\\数据\\render';
const PORT = 9333;
mkdirSync(OUT, { recursive: true });

const url = new URL('file:///' + PAGE.replace(/\\/g, '/')).href;

const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--enable-unsafe-swiftshader',
  '--hide-scrollbars', '--window-size=1500,1150',
  `--remote-debugging-port=${PORT}`, '--no-first-run', '--no-default-browser-check',
  '--allow-file-access-from-files', url,
], { stdio: 'ignore' });

let ws, id = 0;
const pending = new Map();
function send(method, params = {}) {
  const mid = ++id;
  ws.send(JSON.stringify({ id: mid, method, params }));
  return new Promise((res, rej) => pending.set(mid, { res, rej }));
}
async function evalJS(expr) {
  const r = await send('Runtime.evaluate', {
    expression: expr, returnByValue: true, awaitPromise: true,
  });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 300));
  return r.result?.value;
}
async function shot(name) {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(`${OUT}\\${name}`, Buffer.from(r.data, 'base64'));
  console.log('  拍到', name);
}

async function findTarget() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const p = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (p) return p.webSocketDebuggerUrl;
    } catch { /* chrome 还没起来 */ }
    await sleep(250);
  }
  throw new Error('连不上 CDP');
}

const state = () => evalJS(`(() => {
  const cv = document.querySelector('.cvwrap.cv-on');
  if (!cv) return { err: '没有可见的 cvwrap' };
  const dm = [...cv.querySelectorAll('.dmk .dm')];
  const vis = dm.filter(m => m.offsetParent !== null && getComputedStyle(m).display !== 'none');
  return {
    cover: cv.dataset.cv,
    total: dm.length,
    可见: vis.length,
    编号: vis.map(m => m.dataset.no).join(','),
    打灰: dm.filter(m => m.classList.contains('off')).length,
    打灰编号: dm.filter(m => m.classList.contains('off')).map(m => m.dataset.no).join(','),
    首次坐标: vis[0] ? vis[0].style.left + ' / ' + vis[0].style.top : '',
    表格可见行: [...cv.querySelectorAll('tbody tr')].filter(r => r.offsetParent !== null).length,
  };
})()`);

(async () => {
  const wsUrl = await findTarget();
  ws = new WebSocket(wsUrl);
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      const { res, rej } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
    }
  });
  await new Promise(r => ws.addEventListener('open', r, { once: true }));
  await send('Page.enable');
  await send('Runtime.enable');
  await sleep(2500);                       // 等图片和脚本跑完

  // 滚到 001 战场
  await evalJS(`document.getElementById('a001').scrollIntoView({block:'start'}); 1`);
  await sleep(600);

  console.log('\n=== 基线（默认：5 个点 / 3 号位 / 跨阵位不限）===');
  console.log(await state());
  await shot('_chk_1_base.png');

  console.log('\n=== 点「全部」(24) ===');
  await evalJS(`document.querySelector('.nbar button[data-n="24"]').click(); 1`);
  await sleep(400);
  console.log(await state());
  await shot('_chk_2_all.png');

  console.log('\n=== 点「跨阵位对照 = 2 号」===');
  await evalJS(`document.querySelector('.nbar button.slot[data-s="2"]').click(); 1`);
  await sleep(400);
  console.log(await state());
  await shot('_chk_3_slot2.png');

  console.log('\n=== 切机位 cover_1 ===');
  await evalJS(`document.querySelector('.nbar button.cv[data-cv="cover_1"]').click(); 1`);
  await sleep(800);
  console.log(await state());
  await shot('_chk_4_cover1.png');

  console.log('\n=== 切回 cover_3 ===');
  await evalJS(`document.querySelector('.nbar button.cv[data-cv="cover_3"]').click(); 1`);
  await sleep(600);
  console.log(await state());

  ws.close();
  chrome.kill();
  process.exit(0);
})().catch(e => { console.error('失败:', e.message); chrome.kill(); process.exit(1); });
