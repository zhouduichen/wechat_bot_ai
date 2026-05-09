-- 创建数据库（如果还没建的话）
CREATE DATABASE IF NOT EXISTS `shiliu_ai` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `shiliu_ai`;

-- 消息记录表
CREATE TABLE IF NOT EXISTS `messages` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `wx_user_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '微信用户唯一标识（可用备注/手机号等人工映射）',
  `wx_nickname` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '微信昵称',
  `direction` ENUM('in','out') NOT NULL DEFAULT 'in' COMMENT 'in=收到, out=发出',
  `content` TEXT NOT NULL COMMENT '消息内容',
  `is_ai_reply` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为 AI 自动回复',
  `rule_id` BIGINT UNSIGNED NULL DEFAULT NULL COMMENT '命中的规则 ID',
  `is_friend_request` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为好友申请类通知',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_time` (`wx_user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 自动回复规则表
CREATE TABLE IF NOT EXISTS `auto_reply_rules` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `keyword` VARCHAR(255) NOT NULL COMMENT '关键词',
  `match_type` ENUM('contain','equal') NOT NULL DEFAULT 'contain' COMMENT '匹配方式：包含 / 完全匹配',
  `reply_text` TEXT NOT NULL COMMENT '回复内容',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 系统配置表
CREATE TABLE IF NOT EXISTS `settings` (
  `key` VARCHAR(64) NOT NULL,
  `value` TEXT NOT NULL,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 默认开启自动回复
INSERT INTO `settings`(`key`, `value`, `updated_at`)
VALUES ('auto_reply_enabled', '1', NOW())
ON DUPLICATE KEY UPDATE `value` = VALUES(`value`);


