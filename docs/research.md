# 华为接入调研与开源选择

核对日期：2026-10-27。以下区分已核对的官方能力、开源格式参考和项目决策。

## 官方路径

| 路径 | 已核对的信息 | 对 VitalDock 的意义 |
|---|---|---|
| [个人数据副本](https://consumer.huawei.com/cn/support/content/zh-cn16044986/) | 支持电脑隐私中心申请；官方给出准备时间和历史范围说明 | 当前个人场景的首个数据入口 |
| [隐私 FAQ](https://consumer.huawei.com/cn/legal/privacy-questions/faq/) | 获取副本需验证身份、选择服务，并自行设置副本包密码 | 本人操作官方页面、本机解密 |
| [官方 Android Java 示例](https://github.com/HMS-Core/hms-health-demo-java) | 登录授权、读写数据和撤销授权示例；需要应用配置和手机环境 | 后续 Android 桥接参考 |
| [官方 Android Kotlin 示例](https://github.com/HMS-Core/hms-health-demo-kotlin) | 同类移动端接入示例 | 后续移动端实现可选择 Kotlin |
| [REST 运动记录接口](https://developer.huawei.com/consumer/en/doc/HMSCore-References/activityrecords-all-0000001088892993) | 官方存在云侧运动记录 API 文档 | 云侧同步需逐个核实权限及真实响应 |
| [REST 场景示例](https://developer.huawei.com/consumer/de/doc/HMSCore-Guides/heart-rate-alarm-scene-rest-0000001166962091) | 示例请求包含 Bearer 授权、客户端标识，时间示例为纳秒 | 单独编写 REST 适配器；不可套用导出毫秒解析器 |
| [管理用户授权](https://developer.huawei.com/consumer/cn/doc/doccenter-atomic-service/health-add-permissions-as) | 可操作数据取决于获批范围与用户同意范围的交集 | agent 不应取得超出本人授予范围的数据 |
| [申请服务：HarmonyOS 元服务](https://developer.huawei.com/consumer/ru/doc/atomic-guides/health-apply-as) | 对个人开发者列出应用发布、应用类型及数据开放级别等条件 | 说明资格确有约束；Android／REST 条件需在对应控制台另行确认 |
| [订阅数据](https://developer.huawei.com/consumer/cn/doc/hmscore-guides/subscription-0000001078496860) | 订阅通知能力要求企业开发者，个人开发者不能申请 | 个人版不依赖事件订阅，获批后优先评估轮询 |

官方文档按端侧、云侧、HarmonyOS 应用、元服务等区分，不能把其中一种的适用范围泛化到另一种。0.1.0 不承诺个人开发者必然获得某个指标的持续读取资格，也没有实际调用受保护 API。下一阶段以对应地区、产品类型和应用的正式审批结果为依据。

## 开源参考

| 项目及固定版本 | 原目标与可参考部分 | 许可证与本项目处理 |
|---|---|---|
| [CTHRU/Hitrava](https://github.com/CTHRU/Hitrava/tree/6599e43f36fba90d25cc8553154b6f7b5d9e6d27) | 将华为运动记录转为 TCX；参考其副本获取说明及格式覆盖范围 | 当前 NPOSL-3.0，含非营利条件；未复制代码或测试文件 |
| [Huawei-Health-Importer](https://github.com/JordyThien/Huawei-Health-Importer/tree/3f95ecb2a252170976708a90dc26be14efc45c6a) | 导入 Apple Health；核对 `samplePoints`、睡眠键名、体脂和 `sportDataUserData` 结构 | MIT；读取结构与映射参考，以独立 Python 代码实现 |
| [huawei-health-to-health-connect](https://github.com/christianeirich/huawei-health-to-health-connect/tree/6e3fa0e9303110454f81b99aa03311ecacdc90be) | 体重／体脂转 CSV；核对嵌套 JSON 和成员字段 | MIT；格式交叉核对，未引入其 CSV 或 Tasker 实现 |
| [HMS-Core/hms-health-demo-java](https://github.com/HMS-Core/hms-health-demo-java/tree/e6ecc57f5727e2ce6b1794f4cceeaf01ddfbd659) | 官方接入演示；核对登录、撤销、读取能力的边界 | Apache-2.0；仅参考文档，当前无移动端代码复用 |

项目 fixture 全部独立构造，不包含真实个人记录或上游 fixture 的复制。参考项目对不同设备／固件的热量单位仍有待校准信息，因此本项目不把它们的缩放常数当作通用华为定义。运动距离与 HiTrack 轨迹也保留到真实副本验收阶段。

具体结构核对位置：

- [HuaweiSamplePoint.swift](https://github.com/JordyThien/Huawei-Health-Importer/blob/3f95ecb2a252170976708a90dc26be14efc45c6a/HuaweiHealthImporter/HuaweiHealthImporter/Models/HuaweiSamplePoint.swift)
- [HuaweiSportRecord.swift](https://github.com/JordyThien/Huawei-Health-Importer/blob/3f95ecb2a252170976708a90dc26be14efc45c6a/HuaweiHealthImporter/HuaweiHealthImporter/Models/HuaweiSportRecord.swift)
- [HuaweiSleepStage.swift](https://github.com/JordyThien/Huawei-Health-Importer/blob/3f95ecb2a252170976708a90dc26be14efc45c6a/HuaweiHealthImporter/HuaweiHealthImporter/Models/HuaweiSleepStage.swift)

## 为什么独立建仓库

VitalDock 的核心是本地健康数据层和 agent 接口，长期会覆盖多个厂商。现有转换器的产品边界、存储和输出目标不同，适合参考格式，不适合成为整个项目的上游。

如果未来的工作确实以某个项目为主体、长期跟随其更新，fork 可以保留代码历史和上游关系。如果仅引入部分代码，则应按该项目许可证保留署名、许可文本及适用义务，并明确记录改动；是否 fork 不会替代许可证要求。当前选择独立仓库＋独立实现＋参考来源记录，使用 MIT 许可发布自身代码。

## Agent 协议参考

使用[官方 MCP Python SDK 1.x 文档](https://py.sdk.modelcontextprotocol.io/v1/)中的 FastMCP 和 stdio 客户端，明确限制依赖为 1.x。当前官方主文档已有 2.x 接口，升级时需按[官方迁移指南](https://py.sdk.modelcontextprotocol.io/migration/)完成协议和客户端兼容性验收。
