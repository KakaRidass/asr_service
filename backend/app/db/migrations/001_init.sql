-- ============================================
-- 迁移脚本 001: 初始表结构
-- 数据库: MySQL 8.0+
-- 字符集: utf8mb4
-- ============================================

-- 录音记录表
CREATE TABLE IF NOT EXISTS recordings (
    id           CHAR(36)        NOT NULL COMMENT 'UUID',
    filename     VARCHAR(255)    NOT NULL COMMENT '原始文件名',
    file_path    VARCHAR(512)    NOT NULL COMMENT '磁盘路径',
    file_size    BIGINT          NOT NULL COMMENT '字节数',
    file_hash    CHAR(64)        NOT NULL COMMENT 'SHA256（幂等键）',
    mime_type    VARCHAR(64)     NULL     COMMENT 'MIME',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_recordings_hash (file_hash),
    KEY idx_recordings_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='录音文件元数据';

-- 处理任务表
CREATE TABLE IF NOT EXISTS tasks (
    id             CHAR(36)      NOT NULL COMMENT 'UUID',
    recording_id   CHAR(36)      NOT NULL COMMENT '所属录音',
    status         ENUM('pending','transcribing','summarizing','done','failed')
                                  NOT NULL DEFAULT 'pending' COMMENT '任务状态',
    current_stage  VARCHAR(64)   NULL     COMMENT '当前阶段可读描述',
    error_message  TEXT          NULL     COMMENT '失败原因',
    transcript     LONGTEXT      NULL     COMMENT '转写文本',
    summary_json   JSON          NULL     COMMENT '摘要 JSON',
    retry_count    INT           NOT NULL DEFAULT 0 COMMENT '已重试次数',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tasks_recording (recording_id),
    KEY idx_tasks_status (status),
    CONSTRAINT fk_tasks_recording FOREIGN KEY (recording_id)
        REFERENCES recordings (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='处理任务';
