<?php
// 基础配置文件，请根据你的环境修改

// 数据库配置
define('DB_HOST', '127.0.0.1');
define('DB_PORT', '3306');
define('DB_NAME', 'shiliu_ai');
define('DB_USER', 'root');
define('DB_PASS', getenv('DB_PASS') ?: 'YOUR_DB_PASSWORD');
define('DB_CHARSET', 'utf8mb4');

// AI 大模型配置（以 OpenAI / DeepSeek / Dify 为例，可自行替换为其他厂商）
// 可选值：mock / openai / deepseek / dify
define('AI_PROVIDER', 'deepseek');  // 先用deepseek，Dify有401错误

// OpenAI 兼容接口配置
define('OPENAI_API_KEY', 'YOUR_OPENAI_API_KEY_HERE');
define('OPENAI_API_BASE', 'https://api.openai.com/v1');
define('OPENAI_MODEL', 'gpt-4.1-mini');

// DeepSeek 兼容接口配置（请在这里填入你自己的 key）
define('DEEPSEEK_API_KEY', getenv('DEEPSEEK_API_KEY') ?: 'YOUR_DEEPSEEK_KEY');
define('DEEPSEEK_API_BASE', 'https://api.deepseek.com');
define('DEEPSEEK_MODEL', 'deepseek-chat');

// Dify 配置（请填入你的 Dify API Key 和 URL）
define('DIFY_API_KEY', getenv('DIFY_API_KEY') ?: 'YOUR_DIFY_KEY');
define('DIFY_API_BASE', 'http://YOUR_DIFY_SERVER/v1');
define('DIFY_USER', 'wechat_user');  // 用户标识

// 系统基础配置
define('APP_TIMEZONE', 'Asia/Shanghai');
date_default_timezone_set(APP_TIMEZONE);

// 简单的 JSON 输出工具
function json_response($data, int $code = 200)
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}


