<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';

/**
 * 从规则表中查找是否有匹配的关键词回复
 */
function find_rule_reply(string $content): ?array
{
    $pdo = get_pdo();

    // 先查完全匹配，再查包含匹配，简单 MVP 版本
    $sql = "SELECT * FROM auto_reply_rules WHERE is_active = 1 ORDER BY id ASC";
    $stmt = $pdo->query($sql);
    $rules = $stmt->fetchAll();

    $contentLower = mb_strtolower($content, 'UTF-8');
    error_log("=== 规则匹配开始 ===");
    error_log("用户消息原文: '{$content}'");
    error_log("转小写后: '{$contentLower}'");
    error_log("规则总数: " . count($rules));

    foreach ($rules as $rule) {
        $keyword = trim((string)$rule['keyword']);
        if ($keyword === '') {
            error_log("规则ID {$rule['id']}: 关键词为空，跳过");
            continue;
        }
        $kwLower = mb_strtolower($keyword, 'UTF-8');
        error_log("规则ID {$rule['id']}: 关键词='{$keyword}', 小写='{$kwLower}', 类型={$rule['match_type']}");

        if ($rule['match_type'] === 'equal') {
            if ($contentLower === $kwLower) {
                error_log("✓ 完全匹配成功！返回规则ID {$rule['id']}");
                return $rule;
            } else {
                error_log("✗ 完全匹配失败: '{$contentLower}' !== '{$kwLower}'");
            }
        } else { // contain
            if (mb_strpos($contentLower, $kwLower, 0, 'UTF-8') !== false) {
                error_log("✓ 包含匹配成功！返回规则ID {$rule['id']}");
                return $rule;
            } else {
                error_log("✗ 包含匹配失败");
            }
        }
    }

    error_log("未找到任何匹配规则");
    error_log("=== 规则匹配结束 ===");
    return null;
}

/**
 * 简单系统配置读取 / 写入
 */
function get_setting(string $key, $default = null)
{
    $pdo = get_pdo();
    $stmt = $pdo->prepare("SELECT `value` FROM settings WHERE `key` = :k LIMIT 1");
    $stmt->execute([':k' => $key]);
    $row = $stmt->fetch();
    if (!$row) {
        return $default;
    }
    return $row['value'];
}

function set_setting(string $key, string $value): void
{
    $pdo = get_pdo();
    $stmt = $pdo->prepare("
        INSERT INTO settings(`key`, `value`, updated_at)
        VALUES(:k, :v, NOW())
        ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), updated_at = NOW()
    ");
    $stmt->execute([':k' => $key, ':v' => $value]);
}

/**
 * 调用大模型 API（这里以 OpenAI 为例）
 * 如你用国内模型，可在此处替换调用逻辑。
 */
function call_ai(string $prompt, string $userId = ''): string
{
    error_log("=== 调用AI开始 ===");
    error_log("用户消息: '{$prompt}'");
    error_log("AI提供商: " . AI_PROVIDER);
    
    if (AI_PROVIDER === 'mock') {
        return '【自动回复】你刚才说了：' . mb_substr($prompt, 0, 100, 'UTF-8');
    }

    // OpenAI 兼容接口
    if (AI_PROVIDER === 'openai') {
        $url = rtrim(OPENAI_API_BASE, '/') . '/chat/completions';
        $headers = [
            'Content-Type: application/json',
            'Authorization: ' . 'Bearer ' . OPENAI_API_KEY,
        ];

        $payload = [
            'model' => OPENAI_MODEL,
            'messages' => [
                [
                    'role' => 'system',
                    'content' => '你是一个专业的微信私域运营助手，用简洁自然的中文回复用户。',
                ],
                [
                    'role' => 'user',
                    'content' => $prompt,
                ],
            ],
            'temperature' => 0.7,
            'user' => $userId ?: null,
        ];

        return do_llm_request($url, $headers, $payload);
    }

    // DeepSeek（OpenAI 兼容风格）
    if (AI_PROVIDER === 'deepseek') {
        $url = rtrim(DEEPSEEK_API_BASE, '/') . '/chat/completions';
        error_log("请求URL: {$url}");
        $headers = [
            'Content-Type: application/json',
            'Authorization: Bearer ' . DEEPSEEK_API_KEY,
        ];

        $payload = [
            'model' => DEEPSEEK_MODEL,
            'messages' => [
                [
                    'role' => 'system',
                    'content' => '你是一个真人微信客服，回复时遵守以下规则：
1. 回复控制在20字以内，最多不超过40字
2. 直奔主题，不铺垫不寒暄
3. 禁止使用的句式："很高兴...""有什么可以帮您""请问还有什么需要""期待您的回复"
4. 禁止使用的语气词：哈哈、嘿嘿、呢、呀、哟、啦（偶尔用吧/哦可以）
5. 像朋友聊天，不官方，不客套
6. 用户问价格/购买/报名等，给出明确指引
7. 适当用emoji，但一条最多1个',
                ],
                [
                    'role' => 'user',
                    'content' => $prompt,
                ],
            ],
            'temperature' => 0.4,      // 降低发散性，更直接
            'max_tokens' => 60,       // 强制短回复（20字≈40token）
            'user' => $userId ?: null,
        ];

        return do_llm_request($url, $headers, $payload);
    }

    // Dify（对话型应用）
    if (AI_PROVIDER === 'dify') {
        $url = rtrim(DIFY_API_BASE, '/') . '/chat-messages';
        error_log("请求URL: {$url}");
        $headers = [
            'Content-Type: application/json',
            'Authorization: Bearer ' . DIFY_API_KEY,
        ];

        $payload = [
            'inputs' => (object)[],
            'query' => $prompt,
            'response_mode' => 'streaming',
            'user' => $userId ?: DIFY_USER,
            'conversation_id' => '',
        ];

        error_log("Dify payload: " . json_encode($payload, JSON_UNESCAPED_UNICODE));
        return do_dify_request($url, $headers, $payload);
    }

    // 其他厂商可在此扩展
    return 'AI_PROVIDER 未配置正确，请检查 config.php。';
}

/**
 * Dify 专用请求封装
 */
function do_dify_request(string $url, array $headers, array $payload): string
{
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 60);  // 增加超时时间，支持streaming
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($ch, CURLOPT_BUFFERSIZE, 128);  // 小缓冲区，支持流式读取
    curl_setopt($ch, CURLOPT_NOPROGRESS, false);  // 允许进度回调

    $response = curl_exec($ch);
    if ($response === false) {
        $err = curl_error($ch);
        curl_close($ch);
        error_log("cURL错误: {$err}");
        return '抱歉，Dify 服务暂时不可用，请稍后再试～（网络错误：' . $err . '）';
    }
    $statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    error_log("HTTP状态码: {$statusCode}");
    error_log("响应内容长度: " . strlen($response));
    error_log("响应内容: {$response}");

    // 处理空响应
    if (empty($response)) {
        error_log("Dify返回空响应");
        return '抱歉，Dify 服务返回空响应，请检查API配置。';
    }

    // 处理streaming模式的响应（SSE格式）
    if (strpos($response, 'data:') !== false || strpos($response, 'event:') !== false) {
        error_log("检测到streaming模式响应");
        $lines = explode("\n", $response);
        $fullAnswer = '';
        
        foreach ($lines as $line) {
            $line = trim($line);
            if (strpos($line, 'data:') === 0) {
                $jsonStr = trim(substr($line, 5));
                if (empty($jsonStr) || $jsonStr === '[DONE]') {
                    continue;
                }
                
                $data = json_decode($jsonStr, true);
                if (json_last_error() === JSON_ERROR_NONE) {
                    // Dify streaming格式：{"event":"message","answer":"内容"}
                    if (isset($data['answer'])) {
                        $fullAnswer .= $data['answer'];
                    }
                    // 或者 {"event":"agent_message","answer":"内容"}
                    if (isset($data['event']) && $data['event'] === 'agent_message' && isset($data['answer'])) {
                        $fullAnswer .= $data['answer'];
                    }
                }
            }
        }
        
        if (!empty($fullAnswer)) {
            error_log("Dify回复(streaming): {$fullAnswer}");
            error_log("=== 调用AI结束 ===");
            return trim($fullAnswer);
        }
    }

    // 处理blocking模式的响应（JSON格式）
    $data = json_decode($response, true);
    if ($statusCode >= 400 || !is_array($data)) {
        $msg = $data['message'] ?? '未知错误';
        error_log("Dify API错误: {$msg}");
        return '抱歉，Dify 服务请求失败，请稍后再试～（状态码 ' . $statusCode . '：' . $msg . '）';
    }

    // Dify 返回格式：{"answer": "回复内容", "conversation_id": "xxx"}
    $content = $data['answer'] ?? '';
    if (!$content) {
        error_log("Dify返回内容为空");
        error_log("完整响应: " . print_r($data, true));
        return '抱歉，Dify 暂时没有合理的回复。';
    }
    error_log("Dify回复(blocking): {$content}");
    error_log("=== 调用AI结束 ===");
    return trim($content);
}

/**
 * 通用大模型 HTTP 请求封装
 */
function do_llm_request(string $url, array $headers, array $payload): string
{
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 60);  // 增加超时时间，支持streaming
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($ch, CURLOPT_BUFFERSIZE, 128);  // 小缓冲区，支持流式读取
    curl_setopt($ch, CURLOPT_NOPROGRESS, false);  // 允许进度回调

    $response = curl_exec($ch);
    if ($response === false) {
        $err = curl_error($ch);
        curl_close($ch);
        error_log("cURL错误: {$err}");
        return '抱歉，AI 服务暂时不可用，请稍后再试～（网络错误：' . $err . '）';
    }
    $statusCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    error_log("HTTP状态码: {$statusCode}");
    error_log("响应内容: {$response}");

    $data = json_decode($response, true);
    if ($statusCode >= 400 || !is_array($data)) {
        $msg = $data['error']['message'] ?? '未知错误';
        error_log("API错误: {$msg}");
        return '抱歉，AI 服务请求失败，请稍后再试～（状态码 ' . $statusCode . '：' . $msg . '）';
    }

    $content = $data['choices'][0]['message']['content'] ?? '';
    if (!$content) {
        error_log("AI返回内容为空");
        return '抱歉，AI 暂时没有合理的回复。';
    }
    error_log("AI回复: {$content}");
    error_log("=== 调用AI结束 ===");
    return trim($content);
}
