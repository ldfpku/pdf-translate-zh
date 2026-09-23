# models/ —— 插图超分模型（可选）

`sr.py` 用 Real-ESRGAN x4plus（BSD-3，xinntao/Real-ESRGAN）。为控制技能体积，模型**不随技能分发**。

| 文件 | 用途 | 怎么来 |
|---|---|---|
| `RealESRGAN_x4plus.pth` | torch 后端 | 首次超分或 `doctor.py --sr` 自动下载到用户缓存（GitHub → HF 镜像依次尝试，SHA-256 校验）；离线机器手动放进本目录 |
| `RealESRGAN_x4plus.onnx` | onnxruntime 后端（没有 torch 的机器） | 在任一装了 torch 的机器上 `python3 sr.py --export-onnx <路径>`，拷进本目录或设 `PDF_ZH_SR_ONNX` |

`.pth` 的 SHA-256：4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1

内网或国内网络：设环境变量 `PDF_ZH_SR_URL` 指向你自己的镜像（例如对象存储里的一份 .pth），它会排在第一个尝试。
两者都没有时 `sr.py` 退回 Lanczos 放大（非超分），流程不中断，`sr_report.json` 如实记录。
