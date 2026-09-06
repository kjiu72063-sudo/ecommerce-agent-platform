-- ============================================================
-- B1 能力注册中心 - 数据库设计
-- ============================================================
-- 数据库：PostgreSQL 15+
-- 字符集：UTF-8
-- 时区：UTC
-- ============================================================

-- ============================================================
-- 1. 定义对象主表
-- ============================================================
-- 存储所有 8 种定义对象的核心数据
-- 使用 JSONB 存储 spec 和 status，保持灵活性

CREATE TABLE definition_objects (
    -- 主键：带类型前缀的 UUIDv7
    -- 如 agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411
    id VARCHAR(64) PRIMARY KEY,
    
    -- 资源类型：AgentSpec/SkillManifest/ToolManifest/PromptPackage/
    --          ModelPolicy/ContextPolicy/LoopProfile/PermissionProfile
    kind VARCHAR(32) NOT NULL,
    
    -- 人类可读标识：如 programming-agent
    -- 与 namespace + version 形成逻辑唯一键
    key VARCHAR(128) NOT NULL,
    
    -- 命名空间：如 ecommerce, development
    namespace VARCHAR(128) NOT NULL,
    
    -- 语义版本：如 1.0.0, 2.1.3-beta.1
    version VARCHAR(32) NOT NULL,
    
    -- 乐观并发修订号：从 1 开始，每次更新递增
    revision INTEGER NOT NULL DEFAULT 1,
    
    -- 作用域类型：system/tenant/user/project/session
    scope_type VARCHAR(32) NOT NULL,
    
    -- 租户 ID（非系统作用域必须有）
    tenant_id VARCHAR(64),
    
    -- 用户 ID（用户级及以上作用域必须有）
    user_id VARCHAR(64),
    
    -- 项目 ID（项目级和会话级必须有）
    project_id VARCHAR(64),
    
    -- 内容摘要：SHA-256，用于验证 spec 完整性
    content_digest VARCHAR(70) NOT NULL,
    
    -- 核心规格：JSON 格式，结构由 kind 决定
    spec JSONB NOT NULL,
    
    -- 状态信息：phase, observed_revision, reason, activated_at
    status JSONB NOT NULL,
    
    -- 标签：用于查询过滤
    labels JSONB DEFAULT '{}',
    
    -- 注解：用于扩展信息
    annotations JSONB DEFAULT '{}',
    
    -- 创建时间（UTC）
    created_at TIMESTAMPTZ NOT NULL,
    
    -- 创建者信息：actor_type, actor_id, tenant_id
    created_by JSONB NOT NULL,
    
    -- 更新时间（UTC，可选）
    updated_at TIMESTAMPTZ,
    
    -- 逻辑唯一键：同一命名空间下同一 key 同一版本只能有一个
    UNIQUE(namespace, key, version)
);

-- 为什么使用 JSONB 存储 spec？
-- 1. 不同 kind 的 spec 结构不同，JSONB 提供灵活性
-- 2. PostgreSQL 的 JSONB 支持索引和查询
-- 3. 避免为每种 kind 创建独立表
-- 4. Pydantic 模型负责结构验证，数据库负责存储

-- 为什么使用 UNIQUE(namespace, key, version)？
-- 1. 同一技能不同版本可以共存
-- 2. 防止重复注册
-- 3. 支持按 key 查询最新版本


-- ============================================================
-- 2. 索引设计
-- ============================================================

-- 按资源类型查询
CREATE INDEX idx_definition_kind ON definition_objects(kind);

-- 按命名空间和 key 查询（最常用）
CREATE INDEX idx_definition_namespace_key ON definition_objects(namespace, key);

-- 按生命周期阶段查询
CREATE INDEX idx_definition_phase ON definition_objects((status->>'phase'));

-- 按租户查询（多租户隔离）
CREATE INDEX idx_definition_tenant ON definition_objects(tenant_id);

-- 按标签查询（JSONB GIN 索引）
CREATE INDEX idx_definition_labels ON definition_objects USING GIN(labels);

-- 按创建时间排序
CREATE INDEX idx_definition_created ON definition_objects(created_at);

-- 组合索引：按 kind + phase 查询（常用于查询 active 的 AgentSpec）
CREATE INDEX idx_definition_kind_phase ON definition_objects(kind, (status->>'phase'));


-- ============================================================
-- 3. 版本历史表
-- ============================================================
-- 记录每次版本变更，用于审计和回溯

CREATE TABLE definition_versions (
    -- 自增主键
    id SERIAL PRIMARY KEY,
    
    -- 关联的定义对象 ID
    object_id VARCHAR(64) NOT NULL REFERENCES definition_objects(id),
    
    -- 版本号
    version VARCHAR(32) NOT NULL,
    
    -- 修订号
    revision INTEGER NOT NULL,
    
    -- 内容摘要
    content_digest VARCHAR(70) NOT NULL,
    
    -- spec 快照（不可变）
    spec_snapshot JSONB NOT NULL,
    
    -- 创建时间
    created_at TIMESTAMPTZ NOT NULL,
    
    -- 创建者
    created_by JSONB NOT NULL
);

-- 为什么需要版本历史表？
-- 1. 审计：追踪谁在什么时候修改了什么
-- 2. 回溯：可以查看任意历史版本
-- 3. 摘要校验：验证 spec_snapshot 的 content_digest

CREATE INDEX idx_version_object ON definition_versions(object_id);
CREATE INDEX idx_version_created ON definition_versions(created_at);


-- ============================================================
-- 4. 依赖关系表
-- ============================================================
-- 记录定义对象之间的依赖关系

CREATE TABLE definition_dependencies (
    -- 自增主键
    id SERIAL PRIMARY KEY,
    
    -- 源对象 ID（依赖方）
    source_id VARCHAR(64) NOT NULL REFERENCES definition_objects(id),
    
    -- 源对象版本
    source_version VARCHAR(32) NOT NULL,
    
    -- 目标对象 ID（被依赖方）
    target_id VARCHAR(64) NOT NULL REFERENCES definition_objects(id),
    
    -- 目标对象版本
    target_version VARCHAR(32) NOT NULL,
    
    -- 依赖类型：prompt/context/model/loop/permission/skill/tool
    dependency_type VARCHAR(32) NOT NULL,
    
    -- 同一源对象不能对同一目标重复依赖
    UNIQUE(source_id, source_version, target_id, dependency_type)
);

-- 为什么需要依赖关系表？
-- 1. 依赖解析：AgentSpec 启动时需要解析所有依赖
-- 2. 循环检测：防止 A 依赖 B，B 依赖 A
-- 3. 影响分析：修改一个对象时，知道哪些对象受影响

CREATE INDEX idx_dependency_source ON definition_dependencies(source_id, source_version);
CREATE INDEX idx_dependency_target ON definition_dependencies(target_id, target_version);


-- ============================================================
-- 5. 审计日志表
-- ============================================================
-- 记录所有操作，用于安全审计

CREATE TABLE audit_log (
    -- 自增主键
    id SERIAL PRIMARY KEY,
    
    -- 操作时间
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 操作类型：create/update/transition/delete
    action VARCHAR(32) NOT NULL,
    
    -- 资源 ID
    resource_id VARCHAR(64) NOT NULL,
    
    -- 资源类型
    resource_kind VARCHAR(32) NOT NULL,
    
    -- 操作者
    actor_type VARCHAR(32) NOT NULL,
    actor_id VARCHAR(128) NOT NULL,
    
    -- 租户 ID
    tenant_id VARCHAR(64),
    
    -- 变更前状态（JSON）
    before_state JSONB,
    
    -- 变更后状态（JSON）
    after_state JSONB,
    
    -- 变更详情
    details JSONB DEFAULT '{}'
);

CREATE INDEX idx_audit_resource ON audit_log(resource_id);
CREATE INDEX idx_audit_time ON audit_log(created_at);
CREATE INDEX idx_audit_actor ON audit_log(actor_type, actor_id);


-- ============================================================
-- 6. 注释
-- ============================================================

COMMENT ON TABLE definition_objects IS '定义对象主表 - 存储所有 8 种定义对象的核心数据';
COMMENT ON TABLE definition_versions IS '版本历史表 - 记录每次版本变更';
COMMENT ON TABLE definition_dependencies IS '依赖关系表 - 记录定义对象之间的依赖';
COMMENT ON TABLE audit_log IS '审计日志表 - 记录所有操作';

COMMENT ON COLUMN definition_objects.id IS '带类型前缀的 UUIDv7';
COMMENT ON COLUMN definition_objects.spec IS '核心规格，JSON 格式';
COMMENT ON COLUMN definition_objects.status IS '状态信息，包含 phase/observed_revision/reason/activated_at';
COMMENT ON COLUMN definition_objects.content_digest IS 'spec 的 SHA-256 摘要';
