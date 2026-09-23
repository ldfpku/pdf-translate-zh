# 行业识别与行业译法惯例（第 0 步，先于一切翻译）

> **先识别行业，再动翻译。** 工业英语里最危险的词全是日常词：
> jar 不是罐、fish 不是鱼、trip 不是旅行、dope 不是毒品、stall 不是熄火。
> 不锁行业就翻，词词都"对"、句句是外行话。

---

## 1. 识别判据（按证据强度排序）

| 信号 | 怎么读 | 例（本项目实测） |
|---|---|---|
| **标准号族** | 最强信号，一条即可定域 | API RP 7G → 钻柱/钻井作业；ASME Y14.5 → 机械制图（GD&T）；API Spec 7-1/7-2 螺纹代号（NC46、4-1/2 REG/IF）→ 旋转台肩连接 |
| **产品域词汇** | 成簇出现才算数 | mud motor/stator/rotor/power section → 井下动力钻具；jar/detent/accelerator → 震击器 |
| **工况词** | 判子领域与语体 | WOB/ROP/stall/make-up torque → 钻井作业；MT/PT/UT → 无损检测 |
| **单位制** | 判文档谱系 | 英制主导+括注公制（in/psi/ft-lbs 主，mm/N·m 括注）= 美系油田风格，译文照抄双单位、**不换算** |
| **编号体系** | 判文档类型 | 图号=图纸；体系文件编号=体系文件；规范编号=工程规范 |

⚠ 抓标准号的正则要防截断假阳性：`API 3-1/2` 是螺纹代号，
贪婪不足时会截成「API 3-1」，像一条不存在的标准。

**识别结论写进附录 A**：行业/子领域 + 判据证据，读者要能复核。

## 2. 识别后锁三样

1. **行业术语库**：该行业的既定译名接管一切日常词直译（见 §3）。
2. **译法惯例**：术语家族规律（见 §4）—— 规则优先、字典兜底的"规则"来源。
3. **语体**：规范=条文体（应/必须/宜）、手册=操作指令体（祈使句）、
   图纸=标签体（名词短语，不成句）。

## 3. 本项目行业档案：油气钻井装备（井下动力钻具 + 震击器）

**外行必错词表**（每条：en → zh ｜易错点）——

- jar → 震击器｜up-jar/down-jar=上击/下击，jar blow=震击力
- fishing → 打捞｜fishing dimensions=打捞尺寸
- trip in/out → 下钻/起钻｜POOH=起钻；run=下入，re-run=复用
- string → 钻柱｜drillstring/working string
- make up → 上扣｜makeup torque=上扣扭矩；breakout → 卸扣（主动）；back-off → 卸扣松脱（井下意外）
- box / pin → 母扣/公扣｜bit box=钻头母扣（盒是死译）
- 旋转台肩螺纹类型（API Spec 7-2）→ **代号照录、类型用行业名**：REG=正规扣、IF=内平扣、FH=贯眼扣、NC=数字型扣
  （「4-1/2 IF」可写「4-1/2 IF（内平扣）」；「内部平整」「全孔」是字面死译，实测模型会这样错）
- dope → 螺纹脂（动词=涂螺纹脂）
- stall → 憋停｜surface stalling=地面憋停
- WOB → 钻压；ROP → 机械钻速；flow rate → 排量（钻井液语境）
- stabilizer → 扶正器；slips → 卡瓦；elevators → 吊卡；drawworks → 绞车；stand → 立柱
- rat/mouse hole → 鼠洞/副鼠洞
- overpull → 超拉；slack off → 下放；drag → 摩阻（torque and drag=扭矩与摩阻）
- float → 单向阀（BFF=钻头面单向阀）；dump valve → 旁通阀
- lobe → 头数（螺杆马达 lobe configuration=头数配置）
- liner → 衬套（relined stator=重衬定子）
- race → 滚道；play → 游隙（axial play=轴向游隙）；shoulder → 台肩
- galling → 擦伤；washed → 冲蚀；bit balling → 钻头泥包；differential sticking → 压差卡钻
- detent → 液压延时机构（延时芯轴/延时缸）；fire → 触发；cock/re-cock → 复位（蓄势）
- jar latch → 闭锁机构（latched/unlatched=闭锁/解锁）
- dogleg severity → 狗腿度；reaming/backreaming → 扩划眼/倒划眼（机加工语境才是铰孔）
- ⚠ **drill collar → 钻铤**（≠ drill pipe 钻杆）。本项目 规范 G/手册 I 曾误作
  「钻杆」——已列为 V2 重做时的**必改项**，并示范：行业词典要能纠正存量译文。

## 4. 术语家族规律（"规则优先"的规则）

- `*-sub`/adapter → 「××接头」：top sub 上接头、spacer sub 隔离接头、crossover 变径接头
- `* housing` → 「××壳体」：bent/bearing/offset/transmission housing
- `catch` 族 → 「打捞×」：rotor catch 转子打捞头、catch ring 打捞卡环、internal catch 内捞式
- `* ring` **按功能定名不统译**：retaining ring 挡圈、snap ring 卡簧、thrust ring 推力环、O-ring O 形圈
- `*shaft` → 「×轴」：flexshaft 柔性轴、clawshaft 卡爪轴；CV joint=等速万向节
- male/female → 公/母（轴承）；螺纹端专名 pin/box=公扣/母扣
- inner/outer、upper/lower → 内/外、上/下 前置直译
- `-ing` 作业名 → 双字动宾式：milling 磨铣、coring 取心、sliding 滑动钻进
- 工程图标题栏按国标习惯：DRAWN=制图、CHECKED=校对、APPROVED=批准（≠审核）、SCALE=比例、REV=版次、SHEET 1 OF 2=「共 2 张 第 1 张」（不是「第 1/2 页」）；**公司名/商号整体保留原文**，不做半译（「BOREALIS 井下系统」这类半中半英是错的），并写进 WHITELIST
- 商品名/型号/标准号/图号**保留原文**：Loctite、SS100、Super-Jar AP、Safe-Lok；
  「零件名, 型号」复合串零件名译出、型号保留
- **一物一名 + 首现附英文**：全库共用 CORE 词表基座、各册只增不改；
  缩写（WOB/ROP）译名跟缩写走

## 5. 换行业怎么办

本档案只是**第一个行业实例**。换行业（压力容器/焊接/化工…）时：
①按 §1 判据重新识别；②另建该行业的 §3/§4（不要改本档案）；
③客户级词表（术语底座、页眉块、白名单）放在各项目自己的内容层里，每个客户一份，不放进技能。
识别拿不准时，把标准号族 + 产品词簇 + 三句典型原文给用户确认后再动。
