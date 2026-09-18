# 12 - RAG 架构方案（LLM WIKI + 多模态 GraphRAG）

> 目标：把电商售前商品问答从"单源 flat 检索"升级为"多模态、图增强、自纠正、可评估"的 RAG。
> 现状基线：`5a5f872`（2026-09-18，249 passed，分支保护 CI）；现有 `RetrievalPort`/`GeneratorPort` 接缝可作装配边界。
> 状态：方案已确认；落地按阶段切、逐环替换。

## 1. 目标
回答由真实文档/图像/图谱证据支撑；检索质量差时能自我纠正（CRAG）；按查询复杂度走不同检索路径（Adaptive-RAG）。

## 2. 组件 → 层映射
| 层 | 组件 | 职责 |
|---|---|---|
| 文档解析 | Dots.OCR | 商品资料/手册/图像 PDF → 可检索文本 + 保留表格/图像 |
| 多模态嵌入 | GME-Qwen2-VL | 图像/视觉片段 → 多模态向量 |
| 文本嵌入 | bge-large-zh-v1.5 | 中文文本 → 稠密向量 |
| 向量存储 | Milvus | 稠密向量检索（生产级） |
| 词法检索 | BM25 | 稀疏/关键词检索（精确术语） |
| 混合检索 | Hybrid Search | dense + BM25 融合（RRF 或加权） |
| 重排 | Reranker | 对混合召回 top-k 重排 |
| 图增强 | Neo4j GraphRAG | 实体/关系图谱；查询图上下文 |
| 查询路由 | Adaptive-RAG | 简单→稠密/混合；复杂→图谱 |
| 纠错 | Corrective-RAG | 评估检索质量；差则重检索/图，好则生成 |
| 生成 | LLM（glm-5.3 等） | 基于融合证据生成，带引用 |
| 评测 | Ragas | 检索+生成指标（需 ground-truth 集） |

## 3. 核心管道
```text
查询(query)
  → [Adaptive-RAG 路由]  简单?→[Hybrid: bge稠密+BM25]  / 多跳?→[GraphRAG: Neo4j 实体/关系]
  → [合并 + Reranker]
  → [CRAG 质量自评]  → 好→生成｜差→ 纠错重检索(图/外部只读)
  → [LLM 生成]，证据(文档/图像/图路径)带引用
  └→ [Ragas] 离线评测
```

## 4. 与现有代码衔接
- 当前 `ExternalRetrieval` 返回 `{"items":[{source_id, source_version, locator, content, tenant_id, product_id}]}` 平铺证据。
- 需**扩展证据契约**：`graph_context`、`source_type`(text/image/graph)、`rerank_score`、`retrieval_route`(hybrid/graph)、`corrected`(CRAG)。
- 把 `RetrievalPort`/`GeneratorPort` 作为这套 RAG 的装配边界：换实现即接入，不改幂等/保留/装配契约。`GeneratorPort` 侧可能需"工具调用"以做 CRAG 二次检索。

## 5. 关键设计点 / 前置
1. **GraphRAG 图谱构建**：从文档抽实体/关系建 Neo4j schema（最大前置/最重）。
2. **多模态来源**：Dots.OCR + GME-Qwen2-VL 需真实文档/图像语料（当前只有 JSON 知识字段）。
3. **混合融合与重排**：RRF vs 加权；reranker 选型（cross-encoder / bge-reranker）。
4. **CRAG 外部检索边界**：只读知识，严禁副作用。
5. **Ragas 评测集**：人工标注 ground-truth（问题→标准答案/相关证据）。

## 6. 分阶段落地
- **阶段 1（MVP，复用现有 presale）**：Hybrid（bge-large-zh + BM25，Milvus）+ Reranker → 替换当前 `ExternalRetrieval`；`presale-index` 增加文本入库 Milvus + 词法索引。最小闭合、可立刻接 LLM 回答。
- **阶段 2**：Neo4j GraphRAG + Adaptive-RAG 路由。
- **阶段 3**：多模态（Dots.OCR + GME-Qwen2-VL）+ CRAG 自纠。
- **阶段 4**：Ragas 评测闭环（ground-truth 集 + 评测门禁）。
- 每阶段独立可验收、可合并（逐环替换）。

## 7. 风险
- **scope 大**：完整多模态 GraphRAG 是多人数周工作；必须按阶段切。
- **纠正边界**：CRAG 外部检索限只读知识。
- **评测可信度**：无 good ground-truth，Ragas 数字无意义。

## 8. 阶段 1 范围（当前立案）
仅做：**Hybrid 真 RAG on 现有 presale**——bge-large-zh-v1.5（文本稠密）+ BM25（词法）+ Milvus（向量）+ Reranker；替换 `ExternalRetrieval` 实现；`presale-index` 增文本入库；用现有 JSON 知识字段作语料（无需新文档/图像）。
