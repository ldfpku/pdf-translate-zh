# fonts/ —— 可选：固定排版字体

放进这里的字体文件**优先于系统字体**被 `scripts/fontkit.py` 选用。
把同一套字体拷到每台机器的这个目录，各机器产出的排版度量就完全一致。

按文件名识别（大小写不限），常用：

| 角色 | 文件名示例 |
|---|---|
| 中文正文 `zh` | `msyh.ttc`（微软雅黑）、`NotoSansSC-Regular.ttf`、`SourceHanSansSC-Regular.otf` |
| 中文粗体 `zh-bold` | `msyhbd.ttc`、`NotoSansSC-Bold.ttf` |
| 西文粗体 `latin-bold` | `arialbd.ttf`、`LiberationSans-Bold.ttf` |
| 等宽 `mono` | `consola.ttf`、`DejaVuSansMono.ttf` |

注意：ReportLab（语义重排路线）只能用 **TrueType 轮廓**（.ttf / 多数 .ttc）；
.otf（CFF）只供叠印路线使用，重排路线会自动跳过它。

也可以不放文件，改设环境变量：`PDF_ZH_FONT`、`PDF_ZH_FONT_BOLD`（值为字体文件路径，
TTC 可写 `路径#序号`）。`python scripts/fontkit.py` 打印本机实际解析结果。

字体有版权：微软雅黑等系统字体请勿随技能对外分发。
