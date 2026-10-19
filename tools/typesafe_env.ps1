# 只在**当前这个终端会话**里设置 TypeSafe 密钥与开关：不写文件、不写注册表、不回显。
# 用法（在 PowerShell 里**点源**运行，否则变量只在脚本自己的作用域里）：
#     . .\tools\typesafe_env.ps1
# 之后在同一个终端里跑：py -3.11 tests\typesafe_bench.py
# 关掉终端即失效；要持久化请自行 setx TYPESAFE_API_KEY（存进用户环境变量，不在项目目录里）。
$secure = Read-Host "TYPESAFE_API_KEY（输入时不显示）" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:TYPESAFE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
$env:PDF_ZH_TYPESAFE = "1"
if ([string]::IsNullOrWhiteSpace($env:TYPESAFE_API_KEY)) {
    Write-Host "未输入密钥，TypeSafe 保持关闭。"
} else {
    Write-Host ("已设置（长度 {0}，只对本终端有效）。开关 PDF_ZH_TYPESAFE=1。" -f $env:TYPESAFE_API_KEY.Length)
}
