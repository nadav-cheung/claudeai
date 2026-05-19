# RealVNC Server Expert 参数完整参考

来源: https://help.realvnc.com/hc/en-us/articles/360002251297

---

## 连接与端口

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **RfbPort** | `5900` | VNC 监听端口 (1-65535)，企业版需 AllowIpListenRfb=TRUE |
| **AllowIpListenRfb** | `TRUE` (企业版) | FALSE=禁止直接连接，旧名 AllowTcpListenRfb |
| **IpListenAddresses** | 空 (全部) | 限制监听的IP地址，逗号分隔。`0.0.0.0`=仅IPv4，`[::]`=仅IPv6 |
| **IpListenProtocols** | `TCP,UDP` | 限制直接连接使用的协议 |
| **IpClientAddresses** | `+` | IP过滤器：`+`允许 `-`拒绝 `?`标记确认。例：`+192.168.0.1,?192.168.4.0/24,-` |
| **localhost** | `FALSE` | TRUE=仅允许本机VNC Viewer连接 |
| **DaemonPort** | `5999` | Linux虚拟模式守护进程监听端口 |
| **ProxyServer** | 空 | 代理服务器设置，如 `http://proxy:8080` 或 `socks://proxy:8080` |
| **ProxyUserName** | 空 | 代理认证用户名 |

## 认证与安全

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **Authentication** | 空 | 认证方案：`VncAuth`(VNC密码)、`SystemAuth`(系统账户)、`InteractiveSystemAuth`(交互式)、`SingleSignOn`(SSO)、`Certificate`(证书)、`None`(无认证)。可用 `+` 组合多因素，用 `,` 设置备用方案 |
| **Encryption** | `AlwaysOn` | 加密级别：`AlwaysMaximum`(256位AES)、`AlwaysOn`(128位AES)、`PreferOn`、`PreferOff`、`AlwaysOff` |
| **Password** | 空 | VNC密码（混淆格式），用 `vncpasswd -print` 生成 |
| **AuthTimeout** | `900` 秒 | 认证超时时间，0=无限 |
| **BlacklistThreshold** | `5` | 失败认证次数达到后IP被拉黑 |
| **BlacklistTimeout** | `10` 秒 | 黑名单时长，每次翻倍 |
| **Permissions** | 空 | 用户/组权限：`s`查看 `v`仅查看 `k`键盘 `p`鼠标 `c`剪贴板 `t`文件传输 `r`打印 `h`聊天 `d`默认 `f`管理 `!`显式拒绝 `-`禁用。例：`johndoe:skpc,%group:d` |
| **GuestAccessEnable** | `FALSE` | 启用访客登录选项 |
| **GuestPermissions** | 空 | 访客权限，同上格式 |
| **QueryConnect** | `FALSE` | TRUE=有人连接时弹出接受/拒绝提示 |
| **QueryConnectTimeout** | `10` 秒 | 提示显示时间，超时按 QueryTimeoutRights 处理 |
| **QueryTimeoutRights** | 空 | 超时后的权限，空=拒绝连接 |
| **QueryOnlyIfLoggedOn** | `FALSE` | TRUE=仅在有用户已登录时弹出提示 |
| **QueryOfferViewOnly** | `TRUE` | FALSE=隐藏仅查看选项 |
| **RootSecurity** | `FALSE` | TRUE=保护VNC Viewer用户的系统凭据不被非root用户观察 |
| **TlsProfile** | `Normal` | TLS安全强度：`Normal`(TLS 1.2+)、`High`(仅AES-256) |

## 会话控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **AlwaysShared** | `FALSE` | TRUE=允许多用户同时连接 (与 NeverShared/DisconnectClients 配合) |
| **NeverShared** | `FALSE` | TRUE=禁止共享连接 |
| **DisconnectClients** | `TRUE` | 新用户连接时是否断开已有用户 |
| **IdleTimeout** | `3600` 秒 | 空闲断开时间，0=永不 |
| **ConnTimeout** | `0` | 连接最大时长，0=无限制 |
| **DisconnectAction** | `NONE` | 最后用户断开时的动作：`None`(无)、`Lock`(锁定)、`Logoff`(注销/Windows) 或 `StartScreensaver`(屏保/Mac) |
| **MaxDesktops** | 空 | Linux虚拟模式最大桌面数 |
| **ConnectToExisting** | `0` | Linux: `1`=重连回到之前的虚拟桌面 |

## 显示与捕获

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **CaptureMethod** | `0` | 屏幕捕获方法：Windows=`0`(DirectX最优)/`1`(轮询)。macOS=`0`(ScreenCaptureKit/DisplayStream)/`1`(CGScreen)/`2`(DisplayStream)。Linux=`0`(DAMAGE)/`1`(轮询)/`2`(强制DAMAGE) |
| **Desktop** | 空 | 桌面名称，显示在VNC Viewer标题栏 |
| **DisplayDevice** | 空 | Windows: 指定显示器，如 `\\.\Display1`。空=所有显示器 |
| **Monitor** | `-1` | Mac/Linux: 指定显示器编号，0=主显示器。需断开所有会话才生效 |
| **display** | 空 | Linux: X Window显示和屏幕号，如 `:1.0` |
| **CompareFB** | `TRUE` | 像素比较减少不必要更新 |
| **AlwaysShowCursor** | `FALSE` | TRUE=始终显示光标 |
| **BlankScreen** | `FALSE` | TRUE=有连接时空白VNC Server屏幕（保护隐私） |
| **DisableEffects** | `FALSE` | TRUE=禁用字体平滑等视觉效果（提升性能） |
| **RemoveWallpaper** | `FALSE` | TRUE=连接时移除壁纸（提升性能） |
| **RemovePattern** | `FALSE` | TRUE=连接时移除背景图案（提升性能） |
| **UseCaptureBlt** | `TRUE` | FALSE=停止监控半透明窗口更新（提升性能但降低画质） |
| **ServerPreferredEncoding** | `Viewer` | 服务器首选编码，默认以Viewer为准 |
| **AllowDynamicResolution** | `TRUE` | Linux: 允许动态改变虚拟桌面分辨率 |
| **DynamicResolutionMaxSize** | 空 | Linux: 动态分辨率最大尺寸 |

## 输入控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **AcceptKeyEvents** | `TRUE` | FALSE=禁止键盘控制（仅查看模式） |
| **AcceptPointerEvents** | `TRUE` | FALSE=禁止鼠标控制（仅查看模式） |
| **DisableLocalInputs** | `FALSE` | TRUE=有连接时禁用本地键盘鼠标 |
| **AcceptCutText** | `TRUE` | FALSE=禁止VNC Viewer用户粘贴文本到服务器 |
| **SendCutText** | `TRUE` | FALSE=禁止服务器文本被复制到VNC Viewer |
| **SimulateSAS** | `1` | 模拟Ctrl+Alt+Del: `0`=遵从组策略 `1`=默认覆盖 `2`=强制覆盖 |
| **RemapKeys** | 空 | 按键映射/交换。例：`0x22<>0x40`交换`"`和`@`，`0x6d->0x6e`将`m`映射为`n` |
| **LeftCmdKey** | `Alt_L` | Mac: 左Command键映射到的按键码。可选：`Alt_L`/`Alt_R`/`Super_L`/`Super_R`/`ExtendedChars` |
| **LeftOptKey** | `ExtendedChars` | Mac: 左Option键映射 |
| **RightCmdKey** | `Super_L` | Mac: 右Command键映射 |
| **RightOptKey** | `ExtendedChars` | Mac: 右Option键映射 |
| **KeyEventMethod** | `CGPostKeyboardEvent` | Mac: 按键注入方法 `CGPostKeyboardEvent`/`CGEventPost`/`IOHIDPostEvent` |
| **HideOSKWindow** | `FALSE` | TRUE=向VNC Viewer隐藏屏幕键盘 |

## 云连接

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **AllowCloudRfb** | `TRUE` | FALSE=禁止云连接（需重启） |
| **AllowCloudRelay** | `TRUE` | FALSE=禁止通过RealVNC云服务中继的连接 |

## 认证增强 (企业版/专业版)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **RadiusServer** | 空 | RADIUS服务器地址：`host:port,host:port` |
| **RadiusAuthenticationProtocol** | `CHAP` | RADIUS协议：`CHAP`/`PAP` |
| **RadiusNasId** | `vncserver` | RADIUS NAS标识 |
| **RadiusNormalizeUsername** | `FALSE` | TRUE=发送用户名时剥离域前缀 |
| **RadiusPrompt** | `RADIUS password:` | RADIUS认证提示文字 |
| **RadiusPacketInterval** | `1` | RADIUS请求包间隔(秒) |
| **RadiusRequestPackets** | `4` | RADIUS请求包数量 |
| **DuoDeviceChoice** | `BestDevice` | Duo 2FA: `AllDevices`(所有设备列出所有方法)/`BestDevice`(每个方法最优设备) |
| **LdapCertificateUserStore** | 空 | LDAP用户证书存储URL |
| **LdapCertificateTrustStore** | 空 | LDAP信任根证书存储 |
| **LdapCertificateIntermediateStore** | 空 | LDAP中间证书存储 |
| **LdapCertificateRevocation** | `Enforce` | 证书吊销：`CheckIfAvailable`/`Ignore`/`EnforceOcsp` |
| **LdapCertificateCrlLimit** | `26214400` | CRL最大下载字节数 |
| **LdapSecurity** | `Auto` | LDAP安全：`Auto`/`StartTLS`/`None` |
| **KerberosServicePrincipalName** | `host/` | Kerberos服务主体名，如 `host/papaya.dev.acmecorp.com` |
| **WinSsoAccountCheck** | `TRUE` | Windows SSO时执行账户检查 |
| **PamAccountCheck** | `TRUE` | Linux/Mac: FALSE=仅检查PAM认证规则 |
| **PamApplicationName** | `vncserver` | Linux/Mac: 使用自定义PAM配置 |
| **NtLogonAsInteractive** | `FALSE` | TRUE=以交互式登录(类型2)代替网络登录(类型3)，用于域账户权限不足场景 |

## 通知与UI

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **ConnNotifyAlways** | `FALSE` | TRUE=始终显示连接用户名称 |
| **ConnNotifyStyle** | 空 | 通知样式：`Movable`,`Closable`,`Minimizable`,`NoSystem` 组合 |
| **ConnNotifyTimeout** | `4` 秒 | 连接/断开通知显示时长，0=禁用通知 |
| **DisableTrayIcon** | `0` | `0`=始终显示 `1`=无连接时隐藏 `2`=永久隐藏 |
| **DisableAddNewClient** | `FALSE` | TRUE=禁用反向连接菜单选项 |
| **DisableClose** | `FALSE` | TRUE=禁用停止VNC Server菜单选项 |
| **DisableOptions** | `FALSE` | TRUE=禁用选项菜单 |
| **QuitOnCloseStatusDialog** | `FALSE` | TRUE=关闭对话框时停止VNC Server |
| **Locale** | 空 | 界面语言：`en_US`/`fr_FR`/`de_DE`/`es_ES` |
| **PowerWarn** | `TRUE` | TRUE=系统即将休眠或在电池供电时警告 |

## 功能开关

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **ShareFiles** | `TRUE` | FALSE=禁止文件传输 |
| **ClipboardFT** | `TRUE` | FALSE=禁止通过剪贴板传输文件 |
| **EnableRemotePrinting** | `TRUE` | FALSE=禁止远程打印 |
| **AllowChangeDefaultPrinter** | `TRUE` | FALSE=禁止更改默认打印机 |
| **EnableChat** | `FALSE` | TRUE=启用聊天 |
| **AudioEnable** | 空 | 启用音频捕获和传输 |
| **EnableScreenRecording** | `TRUE` | FALSE=禁止录屏 |
| **EnableAutoUpdateChecks** | 空 | `0`=禁用 `1`=自动 `2`=安装时询问 |
| **EnableManualUpdateChecks** | `TRUE` | FALSE=禁用手动检查更新菜单项 |
| **UpdateCheckFrequencyDays** | `1` | 自动检查更新间隔天数 |
| **EnableAnalytics** | `FALSE` | TRUE=允许匿名使用数据收集 |
| **ShowCloudHints** | `True` | 版本6.0.1-6.4.0: FALSE=隐藏云服务注册提示 |
| **ServiceDiscoveryEnabled** | `TRUE` | FALSE=禁止Zeroconf/Bonjour网络广播 |
| **UseLegacyFileTransfer** | `FALSE` | TRUE=使用旧版文件传输代替File Manager |
| **DisableFileTransferAtLockScreen** | `FALSE` | TRUE=锁屏时禁止文件传输 |

## 录制与发言权控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **RecordNotifyAlways** | `FALSE` | TRUE=录屏时持续显示通知 |
| **RecordNotifyDuration** | `4` | 录制通知显示秒数，0=禁用 |
| **RecordQuery** | `FALSE` | TRUE=录屏请求时弹出确认提示 |
| **FloorControlEnable** | `FALSE` | TRUE=同一时间仅一个用户有控制权 |
| **FloorControlAllowLegacyClients** | `1` | 旧客户端：`0`=禁止 `1`=仅查看 `2`=无控制者时可控制 |

## 系统行为

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **ProtocolVersion** | 空 (最新) | RFB协议版本：`3.3`/`3.7`/`3.8`/`4.0`/`4.1`/`5.0`/`6.0`。越低兼容性越好但功能越少 |
| **SystemSleepBehavior** | `PreventWhileConnected` | Mac: `PreventWhileRunning`/`PreventWhileConnected`/`DisconnectViewers`/`DoNothing` |
| **StopUserModeOnSwitchOut** | `TRUE` | Mac: FALSE=用户切换时保持VNC Server运行 |
| **AutoLogonOverride** | `FALSE` | Windows: TRUE=允许Shift键覆盖自动登录 |
| **Dscp** | `0` | 网络流量QoS分类标记 |
| **PollInterval** | `50` ms | Linux: 屏幕更新轮询间隔 |
| **PollCursorTime** | `100` ms | Linux: 光标移动轮询间隔 |
| **DisableAero** | `FALSE` | Windows: TRUE=连接时禁用Aero效果 |

## 日志

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **Log** | 空 | 格式：`活动:目标:级别`。例：`*:file:10,Connections:file:100`。活动用`*`=全部。目标：`stderr`/`file`/`EventLog`(Windows)/`syslog`(Mac/Linux)。级别：0=严重错误，10=审计，30=常规，100=全部 |
| **LogDir** | 空 | 日志目录 |
| **LogFile** | 空 | 日志文件名 |
| **SyslogFacility** | `user` | Linux syslog：`daemon`/`auth`/`authpriv`/`security`/`local0..local7` |

## 其他

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **RandR** | 空 | Linux虚拟模式：分辨率列表，如 `1024x768,1280x1024,800x600` |
| **RsaPrivateKeyFile** | `$HOME/.vnc/private.key` | RSA私钥文件路径 |
