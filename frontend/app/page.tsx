import Link from "next/link";
import Image from "next/image";
import { BrandMark, Icon, type IconName } from "./components/ui-icon";
import { LandingPreview } from "./components/landing-preview";

const features: { id: string; icon: IconName; name: string; title: string; description: string; points: string[] }[] = [
  { id: "knowledge", icon: "book", name: "知识问答", title: "答案有依据，知识用得上。", description: "从企业资料中寻找答案，让制度、流程和内部指南成为随时可用的知识。", points: ["选择当前空间内可访问的知识库", "回答附带引用，点击查看原文摘录", "证据不足时明确提示，不猜测结论"] },
  { id: "assistant", icon: "sparkles", name: "智能助手", title: "从一个问题，到下一步行动。", description: "用自然语言提出需求。助手根据已配置的能力回答问题、查询信息，或发起需要审核的操作。", points: ["在当前空间选择可用的智能体", "查询信息与知识问答在同一入口完成", "IT 权限申请先审核，再执行"] },
  { id: "approvals", icon: "shield", name: "审批中心", title: "关键操作，让人来把关。", description: "集中查看 IT 权限申请。申请内容、审批决定与执行结果分别呈现，让每一步都有清晰的状态。", points: ["申请人查看自己的申请与处理进度", "有权限的审核者确认申请内容", "审批通过后，单独跟踪执行结果"] },
  { id: "logs", icon: "list", name: "执行日志", title: "看见过程，定位问题。", description: "管理员从执行记录中了解智能体与工具的调用情况，按条件筛选，再展开查看详情。", points: ["按状态和记录类型快速筛选", "查看调用耗时、结果与关联审批", "日志仅在授权的工作空间内可见"] },
  { id: "evaluation", icon: "layers", name: "评测数据集", title: "用可重复的评测，检验表现。", description: "管理测试用例，运行小规模评测，从通过率、覆盖率和耗时了解智能体的结构化行为。", points: ["组织知识、工具与权限边界用例", "查看历史运行与预期、实际结果", "工具仅模拟验证，数据发送前需确认"] },
  { id: "workspace", icon: "users", name: "工作空间", title: "团队各司其职，空间各有边界。", description: "在独立的工作空间中组织成员与资源。切换空间后，功能与内容随当前身份和权限同步更新。", points: ["一个入口切换不同工作空间", "按员工、知识、智能体及系统管理员分工", "成员与资源保持工作空间隔离"] },
];

export default function Home() {
  return <div className="landing">
    <Link className="skip-link" href="#main">跳至主要内容</Link>
    <header className="landing-header"><div className="landing-nav">
      <Link className="landing-brand" href="/" aria-label="企业 AI 工作台首页"><BrandMark /><strong>企业 AI 工作台</strong></Link>
      <nav aria-label="首页导航"><Link href="#overview">平台概览</Link><Link href="#features">功能模块</Link><Link href="#guide">使用指南</Link></nav>
      <Link className="primary-button compact-button" href="/app">进入平台 <Icon name="arrow" /></Link>
    </div></header>
    <main id="main">
      <section className="landing-hero" id="overview"><div className="landing-container hero-grid">
        <div className="hero-copy"><p className="landing-kicker"><span /> 为企业而建的 AI 工作空间</p>
          <h1>让企业知识可问，<br /><span>业务操作可控。</span></h1>
          <p className="hero-description">连接知识、智能助手与业务流程。<br className="desktop-break" />在清晰的权限边界内，让 AI 成为团队的工作伙伴。</p>
          <div className="hero-actions"><Link className="primary-button" href="/app">开始使用 <Icon name="arrow" /></Link><Link className="secondary-button" href="#features">了解平台功能</Link></div>
          <p className="hero-note"><Icon name="shield" /> 知识有据 · 操作有审 · 过程可查</p>
        </div>
        <div className="hero-art"><Image src="/images/hero-knowledge.png" alt="蓝色文档、知识节点与连接轨道组成的抽象插画" width={1536} height={1024} priority sizes="(max-width: 760px) 100vw, 58vw" /></div>
      </div></section>
      <section className="landing-intro landing-container" id="features"><p className="landing-kicker">从知识到行动</p><h2>一个平台，串起工作的每一步。</h2><p>六个相互连接的模块，让使用、审核与运营都有自己的位置。</p>
        <nav className="module-index" aria-label="功能模块索引">{features.map(feature => <Link href={`#${feature.id}`} key={feature.id}><Icon name={feature.icon} /><span>{feature.name}</span></Link>)}</nav>
      </section>
      {features.map((feature, index) => <section className={`landing-feature ${index % 2 ? "feature-tinted" : ""}`} id={feature.id} key={feature.id}>
        <div className={`landing-container feature-grid ${index % 2 ? "feature-reverse" : ""}`}>
          <div className="feature-copy"><p className="landing-kicker"><Icon name={feature.icon} /> {String(index + 1).padStart(2, "0")} / {feature.name}</p><h2>{feature.title}</h2><p>{feature.description}</p><ul>{feature.points.map(point => <li key={point}><Icon name="check" />{point}</li>)}</ul><Link className="feature-link" href="/app">进入平台体验 <Icon name="arrow" /></Link></div>
          <LandingPreview module={feature.id} />
        </div>
      </section>)}
      <section className="landing-guide landing-container" id="guide"><p className="landing-kicker">使用指南</p><h2>从这里，开始你的第一步。</h2><div className="guide-steps">
        {[ ["01", "登录并选择空间", "使用已有账号进入平台，选择你有权限访问的工作空间。"], ["02", "向智能助手提问", "选择可用的智能体，提出问题；查询知识时，可进一步查看引用依据。"], ["03", "跟进结果与审核", "在审批中心跟进申请。管理员可通过日志与评测了解运行表现。"] ].map(([number, title, copy]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p></article>)}
      </div><details className="landing-faq"><summary>为什么不同成员看到的功能不同？</summary><p>功能入口根据当前工作空间中的角色显示。员工可使用已授权的助手与知识库；执行日志和评测面向智能体或系统管理员，成员管理由系统管理员操作。</p></details><details className="landing-faq"><summary>首页的演示可以执行真实操作吗？</summary><p>首页展示的是交互示例，使用合成内容，不连接业务系统。真实操作需要登录平台，并遵循现有权限和审批流程。</p></details></section>
      <section className="landing-cta"><div className="landing-container"><div><p className="landing-kicker">准备开始</p><h2>让 AI 进入团队的日常工作。</h2><p>从一个问题开始，找到答案，推进下一步。</p></div><Link className="primary-button" href="/app">进入企业 AI 工作台 <Icon name="arrow" /></Link></div></section>
    </main>
    <footer className="landing-footer landing-container"><Link className="landing-brand" href="/"><BrandMark /><strong>企业 AI 工作台</strong></Link><p>知识 · 协作 · 可控执行</p><Link href="#overview">返回顶部 ↑</Link></footer>
  </div>;
}
