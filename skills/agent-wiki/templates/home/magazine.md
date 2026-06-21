<!-- agent-wiki 首页布局模板 · 杂志风。挑选片段贴入 wiki/index.md；_待补充_ 由 agent 填写，🗂 工作区卡片块原样照搬。 -->

# Wiki Index · 杂志

> [!quote] 导语
> _待补充_：一句话点题，串起本库的研究气质。

## 🧭 动态视图（Bases）

![[index.base#主题总览]]

## 📚 主题导航

> [!tip] 研究方向速览
> _待补充_：四大方向各一行，点名代表主题与篇数。

## 🔗 主题关系图谱

> [!quote] 脉络
> _待补充_：以叙述串联主题间的关系。

## 🗂 工作区

<!-- agent-wiki:auto start -->
> [!abstract] 由 agent-wiki 自动维护（Dataview 动态卡片）
> 检索报告 / 图谱 由 Dataview 实时扫描 `queries`、`graphs` 文件夹，新增文件自动出现，无需手改。

```dataviewjs
const root = dv.current().file.folder;
const groups = [
  { title: "🔎 检索报告", dir: root + "/queries", ext: "md" },
  { title: "🕸 图谱", dir: root + "/graphs", ext: "canvas" },
];
const style = dv.container.createEl("style");
style.textContent = `
.aw-grid{display:flex;flex-wrap:wrap;justify-content:center;gap:.75rem;margin:.5rem 0 1.25rem}
.aw-card{flex:1 1 168px;max-width:232px;min-height:44px;display:flex;align-items:center;justify-content:center;text-align:center;padding:.7rem .9rem;border:1px solid var(--background-modifier-border);border-radius:12px;background:var(--background-secondary);color:var(--text-normal);text-decoration:none;font-weight:500;box-shadow:0 1px 2px rgba(0,0,0,.06);transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
.aw-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.12);border-color:var(--interactive-accent)}
.aw-card:focus-visible{outline:2px solid var(--interactive-accent);outline-offset:2px}
.aw-card:active{transform:translateY(0)}
@media (prefers-reduced-motion:reduce){.aw-card{transition:none}}
`;
for (const g of groups) {
  dv.header(3, g.title);
  const files = app.vault.getFiles()
    .filter(f => f.extension === g.ext && f.path.startsWith(g.dir + "/"))
    .sort((a, b) => a.basename.localeCompare(b.basename));
  if (!files.length) { dv.paragraph("_（空）_"); continue; }
  const grid = dv.container.createEl("div", { cls: "aw-grid" });
  for (const f of files) {
    const card = grid.createEl("a", { cls: "internal-link aw-card", href: f.path });
    card.dataset.href = f.path;
    card.setText(f.basename);
  }
}
```
<!-- agent-wiki:auto end -->
