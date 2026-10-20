# 惊慌动作的实际参考与调整

本次下载公开 GIF 到临时目录逐帧观察，项目中保存来源链接和原创重绘图集。

| 参考 | 观察 | 本项目采用的动作结构 |
| --- | --- | --- |
| [《幸运星》Misao 甩臂片段](https://tenor.com/view/lucky-star-misao-kusakabe-annoyed-prince-gif-27187406) | GIF 有 7 帧，每帧 60 毫秒。手臂在头顶与身侧之间迅速甩动，中间姿势经过水平位置，身体配合摆动。 | 抬高双手 → 水平经过 → 下摆至身侧 → 水平经过 → 再抬高，形成清楚的摆臂弧线。 |
| [阿库娅空中慌乱片段](https://tenor.com/view/aqua-konosuba-panic-spin-scream-gif-25524282) | GIF 有 31 帧，每帧 100 毫秒。手臂、头胸与身体倾斜方向错开，头发跟随身体运动。 | 交错蹬腿、头胸反摆、衣摆与头发略滞后，配合睁大的蓝眼和张嘴表情。 |

上一版双手主要缩在胸前，腿部变化也偏小。这次沿用更早的原创惊慌立绘作为身份与表情参考，将手臂活动范围扩大到头顶和身侧。参考片段只用于研究动作；项目中的角色图仍由本项目原角色重绘。

新图集包含 8 张原创姿势。播放顺序为 `0, 1, 2, 1, 3, 4, 5, 6, 7`，每个时间步 80 毫秒，循环共 0.72 秒。重复一次水平经过帧，用于连接下摆和抬臂；这样不会从手臂落下直接跳到举过头顶。

- 当前图集：[companion-drag-anime-v3.png](../web/assets/companion-drag-anime-v3.png)
- 内置 imagegen 完整提示词：[companion-drag-anime-v3-prompt.json](companion-drag-anime-v3-prompt.json)
- 实际渲染动作预览：[companion-motion-preview.html](companion-motion-preview.html)

自动打哈欠／伸懒腰至少间隔 5 分钟，启动后的第一次也等待 5 分钟。工作和拖动期间延后，手动播放后重新开始计时。
