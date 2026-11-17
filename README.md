# AgRelay 下载与安装

在 Mac 本地授权项目，通过 SSH 使用 VPS 上的原版 Claude Code，让其通过 AgRelay 工具读取、编辑本地代码并运行受限 Python 测试。

这里是公开下载仓库，提供安装入口、二进制和随包文档。产品源码仓库保持私有；本仓库不是完整源码。当前版本 **0.2.8-mvp-dev** 是受限预发行版。

## 一行安装

在 Mac 的系统 Terminal 中运行：

```sh
curl -fsSL https://raw.githubusercontent.com/lajidonggua/AgRelay-releases/main/install.sh | sh
```

需要 Apple Silicon Mac 和已有 Python3.9+。无需 GitHub 登录、Go、Swift 或 sudo；不自动安装依赖。安装程序校验固定版本安装器的内置 SHA-256、归档和包内文件。校验确认内容一致性，不是发布者签名；当前二进制未签名或公证，不应绕过系统安全提示。

安装位置为 `~/.agrelay-app/0.2.8-mvp-dev`，启动命令为 `~/.local/bin/agrelay`。不改 Shell 配置，不覆盖已有安装，也不自动连接 VPS 或调用模型。已有同一版本时无需重复安装。

## 配置一次，然后使用

先准备好 Ubuntu ARM64 VPS 的地址、端口、用户名和已有登录密钥，并在该用户下安装、配置好原版 Claude Code **2.1.318**。AgRelay 不询问或保存模型 API Key。

```sh
export PATH="$HOME/.local/bin:$PATH"
agrelay setup
cd /absolute/path/to/your/project
agrelay start --edit
```

setup 默认选择“直接填写服务器”，依次填写 IP/域名、端口、用户名，选择1Password/SSH Agent或本机密钥文件，并填写VPS上Claude的绝对路径。无需修改 `~/.ssh/config`；已有别名可选择另一入口。首次服务器ED25519完整指纹需从云控制台或已可信会话核对取得；向导只接受完全匹配的服务器公钥。Agent模式会列出密钥名称和指纹供选择；私钥仍由Agent保管。项目启动时按本机提示输入 `TRUST 短编号`；进入 Claude 后输入 `/mcp` 确认 agrelay 已连接，再提出任务。`agrelay` 默认只读，`--edit` 允许普通源码编辑，`--edit --execute` 额外启用逐命令 Mac 审批的受限执行。退出用 `/exit`，恢复用 `agrelay resume --last`，每次运行最长20分钟。

代码、项目指令、diff 和输出可能到达 VPS、模型及原生历史或缓存；请选适合这一数据流的项目。未知硬编码秘密不能全部识别。真实授权以 Mac 本地为准，远程终端里的“已批准”文字没有授权效力。

当前原生终端验证组合为系统 Terminal build488.9。执行仅支持 Python3.14.5、macOS27.2/26B123 或27.2.1/26B131 的 Python 标准库只读快照；通用 Shell、第三方包、网络、子进程和写文件型构建保持关闭。未知组合不会自动放宽限制。无需执行时不加 `--execute`。

```sh
agrelay doctor --execution  # 本机假样例检查，不连接 VPS
```

## 手动下载、检查与卸载

[固定版本发布包](https://github.com/lajidonggua/AgRelay-releases/releases/tag/v0.2.8-mvp-dev) 包含二进制归档、SHA-256、安装程序。归档内有快速开始、用户指南和验证范围。包内旧文档中的源码下载链接可能需要权限；免登录安装以本页为准。此公开包与原仓库已验证的0.2.8二进制完全一致。

希望先查看脚本时，可以保存固定版本入口再运行：

```sh
curl -fL https://raw.githubusercontent.com/lajidonggua/AgRelay-releases/v0.2.8-mvp-dev/install.sh -o agrelay-install.sh
sh agrelay-install.sh
```

安装停止时保留已有文件。卸载请使用本仓库固定版本的 `install.py`（也在发布资产内）：

```sh
python3 -I -S -B install.py --uninstall --prefix "$HOME/.agrelay-app/0.2.8-mvp-dev"
```

仅删除清单匹配的自有二进制和启动器；保留项目、AgRelay 控制状态、SSH 配置及 Claude 原生会话。没有自动升级或自动删除项目功能。
