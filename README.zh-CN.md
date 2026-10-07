# Sleepless Guard

[English documentation](README.md) · **源码测试版 v0.1.0-beta.1**

一个让 MacBook 按需保持运行、并在任务结束后恢复正常休眠的菜单栏工具。支持**简体中文、繁体中文、英文**，随系统语言选择。基于 Adam Boudjemaa 的 [Sleepless v1.2.7](https://github.com/Aboudjem/Sleepless)，保留 MIT 许可证，并增加独立守护程序。不是上游官方版本，也不是 Apple 产品。

软件免费，费用 **人民币 ¥0**。无需账号、订阅、Homebrew 或第三方 Python 依赖；运行时不联网，不上传使用数据。源码构建需要 Apple Command Line Tools。GitHub 下载可能受所在网络影响；请优先使用本仓库或上游的原始来源。

## 语言

应用根据 macOS 为应用选择的语言或系统首选语言，加载英文、简体中文或繁体中文；其他语言回退到英文。在 macOS 中修改应用语言后，请退出并重新打开应用。安装脚本与主要公开文档使用英文。翻译文件位于 `locales/`，三种语言各有完整的 27 项界面与通知文本，显示名称也已本地化。

## 使用方式与保护规则

| 情况 | 行为 |
| --- | --- |
| 正常打开应用 | 不会自动开启防休眠；由你手动打开开关 |
| 电池供电开启任务 | 最长 2 小时；电量 ≤ 30% 时请求恢复正常休眠 |
| 接电开启任务 | 最长 12 小时；拔电后结束本次接电任务 |
| 电池任务中插电 | 仍保留最初的 2 小时上限，不借此延长任务 |
| 选择 1 小时或 2 小时 | 应用的计时器进一步限制任务时长 |
| 退出应用或应用异常结束 | 应用或独立守护程序请求恢复正常休眠 |
| 守护程序重新启动 | 先请求恢复正常休眠，不自动续接上一次任务 |

守护程序通常每 5 秒检查一次，实际响应受系统调度和命令执行影响。应用可将电量底线调高到 50%；界面中的“默认上限”仍受独立守护程序的 2/12 小时上限约束。安装后守护程序随登录运行，菜单栏应用的登录启动默认关闭。

## 必须了解的限制

本工具使用 macOS 的全局 `pmset -a disablesleep` 开关，其中 `disablesleep` 是未写入官方手册的行为，系统升级可能改变效果。它会影响整台电脑的系统休眠；不会创建虚拟显示器，不修改屏幕分辨率，不通过显示断言强制亮屏。

**关闭防休眠只是允许正常休眠，不等于立即让电脑睡着。** 腾讯会议等其他程序仍可能阻止息屏或休眠。本工具不强制结束这些程序。不要与其他会控制 `disablesleep` 的工具一起运行，包括另一份 Sleepless；全局开关没有所属应用，多个控制器会相互影响。

**电脑运行时不要放进封闭的包里。** 请保持通风，收包前结束任务、使用 Apple 菜单中的“睡眠”并确认电脑停止运行。本项目**没有温度传感器监测或过热关机功能**，不能保证一定不会发热、掉电或丢失任务。

这次公开版的完整 GUI 验收和实际合盖/开盖测试仍待完成；策略自动测试通过不等于你的机器已经验证。请先用不重要的测试任务验收，详见 [验证记录与手工检查](docs/VALIDATION.md)。

## 构建与安装

目前支持 **Apple Silicon MacBook + macOS 26 及以上**。需要 Apple Command Line Tools 中的 `swiftc`、`codesign` 和 `/usr/bin/python3`。

```sh
xcode-select --install
git clone https://github.com/stevechen256-source/Sleepless-Guard.git
cd Sleepless-Guard
./install.sh --dry-run
```

`--dry-run` 只显示将使用的路径，不编译、不安装、不请求管理员授权、不改变休眠设置。确认后自行执行：

```sh
./install.sh
open "$HOME/Applications/SleeplessCN.app"
```

安装器会本地编译，明确询问后为当前用户安装两条特定 `pmset` 命令的授权，并安装应用与守护程序。安装器不会打开应用或开启防休眠。整个安装脚本**不要加 sudo**；需要权限的步骤会单独请求。

这是本地 ad-hoc 签名的源码版本，没有 Developer ID 签名或 Apple 公证。不要为它关闭 Gatekeeper 或 SIP。仅编译可运行 `./build.sh`；单独打开未安装守护程序的构建产物，不能启用防休眠。

## 安装位置与权限

- 应用：`~/Applications/SleeplessCN.app`
- 守护程序与本地状态：`~/Library/Application Support/SleeplessCN/`
- 守护启动项：`~/Library/LaunchAgents/io.github.sleeplesscn.guard.plist`
- 独立授权：`/etc/sudoers.d/sleeplesscn-<当前用户数字ID>`

只允许当前用户免重复密码运行 `/usr/bin/pmset -a disablesleep 0` 和 `1`，不授权任意命令或不受限制的 `pmset`。该权限属于当前用户，因此其他以相同用户运行的程序也能调用这两条命令。详见 [SECURITY.md](SECURITY.md)。

安装器不覆盖已有目标。测试版升级请先卸载本衍生版，再重新安装。原版 Sleepless 不会被替换，其共享授权文件也不会被删除。保留内部 `SleeplessCN` 文件名是为了与上游隔离。

## 恢复与卸载

点击开关，或选择“退出并恢复休眠”。也可以在源码目录运行：

```sh
./restore-sleep.sh
```

它只请求恢复允许休眠，不会立刻打断正在进行的工作让电脑睡着。需要收包时，请自行选择 Apple 菜单 → 睡眠。

卸载前保留源码目录，运行：

```sh
./uninstall.sh --dry-run
./uninstall.sh
```

卸载器先验证归属并恢复允许休眠，再退出应用、移除本工具登录项、停止守护并删除本工具自己的文件和授权。无法恢复休眠或应用没有退出时会停止，不会虚报成功。支持目录里不认识的其他文件会保留；其他工具的授权不会被删除。

## 测试与许可

```sh
/usr/bin/python3 scripts/guard.py --self-test
/usr/bin/python3 -m unittest discover -s tests -v
```

测试不运行真实安装器、不修改电源设置。问题反馈请提供系统版本、芯片、电源状态和复现步骤，并移除用户名、完整家目录、凭据、私人笔记和日志。

本项目遵循 [MIT 许可证](LICENSE)，保留原作者 Adam Boudjemaa 的版权和[来源说明](NOTICE.md)。软件按现状提供，不提供任何担保。
