"""从桌宠实际渲染帧生成可暂停的单文件预览和静态检视图。"""
import json
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication
from pet_animation import CLIPS
from pet_assets import load_pet_frames, SEQUENCES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quality', choices=('smooth', 'pixel'), default='smooth')
    args = parser.parse_args()
    app = QApplication(['pet-motion-preview'])
    frames = load_pet_frames(ROOT / 'web/assets', quality=args.quality, device_pixel_ratio=2)
    titles = {'drag': '拖动 · 大幅甩臂与交错蹬腿', 'greet': '点击 · 抬手挥动',
              'cheer': '完成 · 一次欢呼', 'stretch': '待机 · 伸个懒腰',
              'recover': '松手 · 站稳恢复'}
    records = []
    for key, title in titles.items():
        clip = CLIPS[key]
        images = []
        for frame in clip.frames:
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            frames[frame].save(buffer, 'PNG')
            images.append('data:image/png;base64,' + bytes(data.toBase64()).decode('ascii'))
        records.append({'title': title, 'frameMs': clip.frame_ms, 'images': images,
                        'uniqueFrames': len(set(clip.frames)), 'loop': clip.loop})

    html = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>故事海同伴 · 动作预览</title>
<style>
body{margin:0;background:#eef6f7;color:#19364b;font:15px system-ui,sans-serif}
main{max-width:1050px;margin:32px auto;padding:20px}h1{font-size:24px}
p{line-height:1.7;color:#526b78}button,select,input{font:inherit;accent-color:#329da9}
button,select{background:white;border:1px solid #b8d7dd;border-radius:8px;padding:8px 12px}
nav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:22px 0}
section{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px}
article{background:white;border:1px solid #d3e6e9;border-radius:18px;padding:14px;text-align:center}
h2{font-size:15px;margin:4px 0 14px}.sprite{display:block;width:128px;height:192px;margin:0 auto 16px;image-rendering:RENDERING}
small{display:block;min-height:30px;color:#607b88}input{width:100%;cursor:pointer}
</style><main><h1>故事海同伴 · 动作中间帧</h1>
<p>这里使用桌宠实际显示的QUALITY帧。可以暂停、降低速度，或拖动每组下方的滑块逐帧查看。预览循环仅用于演示；桌面上的自动打哈欠至少间隔五分钟。桌宠右键“显示画质”可随时切回上一版像素效果。</p>
<nav><button id="toggle">暂停</button><label>播放速度 <select id="speed">
<option value=".5">0.5 倍</option><option value=".75">0.75 倍</option>
<option value="1" selected>1 倍</option></select></label></nav><section id="cards"></section></main>
<script>
const records=RECORDS;
let playing=true,speed=1,last=performance.now();
const cards=records.map(record=>{
 const article=document.createElement('article'),title=document.createElement('h2'),img=document.createElement('img'),info=document.createElement('small'),slider=document.createElement('input');
 title.textContent=record.title;img.className='sprite';img.alt=record.title;slider.type='range';slider.min=0;slider.max=record.images.length-1;slider.value=0;
 article.append(title,img,info,slider);document.querySelector('#cards').append(article);
 const card={record,img,info,slider,elapsed:0,index:0};
 slider.addEventListener('input',()=>{playing=false;document.querySelector('#toggle').textContent='继续';card.index=+slider.value;card.elapsed=card.index*record.frameMs;render(card)});
 return card;
});
function render(card){card.img.src=card.record.images[card.index];card.slider.value=card.index;card.info.textContent=(card.index+1)+' / '+card.record.images.length+' · '+card.record.uniqueFrames+' 张姿势'}
cards.forEach(render);
document.querySelector('#toggle').onclick=()=>{playing=!playing;document.querySelector('#toggle').textContent=playing?'暂停':'继续'};
document.querySelector('#speed').onchange=e=>speed=+e.target.value;
function tick(now){const delta=Math.min(100,now-last);last=now;if(playing)for(const card of cards){const length=card.record.images.length,cycle=length*card.record.frameMs+(card.record.loop?0:900);card.elapsed=(card.elapsed+delta*speed)%cycle;const index=Math.min(length-1,Math.floor(card.elapsed/card.record.frameMs));if(index!==card.index){card.index=index;render(card)}}requestAnimationFrame(tick)}
requestAnimationFrame(tick);
</script></html>""".replace('RECORDS', json.dumps(records, ensure_ascii=False)).replace(
        'RENDERING', 'auto' if args.quality == 'smooth' else 'pixelated').replace(
        'QUALITY', '原素材高清' if args.quality == 'smooth' else '低分辨率像素')
    (ROOT / 'docs/companion-motion-preview.html').write_text(html)

    sheet = QImage(8 * 128, 5 * 224, QImage.Format.Format_ARGB32)
    sheet.fill(QColor('#f4f8f8'))
    painter = QPainter(sheet)
    painter.setPen(QColor('#19364b'))
    painter.setFont(QFont('sans-serif', 10))
    for row, (key, title) in enumerate(titles.items()):
        painter.drawText(QRect(8, row * 224, 1000, 26), Qt.AlignmentFlag.AlignVCenter, title)
        sequence = SEQUENCES['wave' if key == 'greet' else key]
        for i, frame in enumerate(sequence):
            painter.drawPixmap(i * 128, row * 224 + 28, frames[frame])
    painter.end()
    sheet.save(str(ROOT / 'docs/companion-motion-preview.png'))
    print('已生成 docs/companion-motion-preview.html 和 docs/companion-motion-preview.png')


if __name__ == '__main__':
    main()
