<?php
// Python 客户端调用此接口，将微信新消息传进来
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/ai_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['error' => 'Method not allowed'], 405);
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!is_array($data)) {
    $data = $_POST; // 兼容表单
}

$content = trim((string)($data['content'] ?? ''));
$wxUserId = trim((string)($data['wx_user_id'] ?? ''));
$wxNickname = trim((string)($data['wx_nickname'] ?? ''));
$isFriendRequest = (int)($data['is_friend_request'] ?? 0);

if ($content === '' && !$isFriendRequest) {
    json_response(['error' => 'content is empty'], 400);
}

try {
    $pdo = get_pdo();
    $pdo->beginTransaction();

    // 记录收到的消息
    $stmt = $pdo->prepare("
        INSERT INTO messages (wx_user_id, wx_nickname, direction, content, is_friend_request, created_at)
        VALUES (:uid, :nick, 'in', :content, :fr, NOW())
    ");
    $stmt->execute([
        ':uid' => $wxUserId,
        ':nick' => $wxNickname,
        ':content' => $content,
        ':fr' => $isFriendRequest,
    ]);
    $inMsgId = (int)$pdo->lastInsertId();

    $autoOn = get_setting('auto_reply_enabled', '1') === '1';
    $replyText = '';
    $usedRuleId = null;

    if ($autoOn) {
        // 先规则匹配
        $rule = find_rule_reply($content);
        if ($rule) {
            $replyText = (string)$rule['reply_text'];
            $usedRuleId = (int)$rule['id'];
            // 调试信息
            error_log("匹配到规则ID: {$usedRuleId}, 关键词: {$rule['keyword']}, 回复: {$replyText}");
        } else {
            // 没有规则就走 AI（如果启用了AI）
            $aiEnabled = get_setting('ai_enabled', '1') === '1';
            if ($aiEnabled) {
                error_log("未匹配到规则，调用AI，用户消息: {$content}");
                $replyText = call_ai($content, $wxUserId);
                error_log("AI返回: {$replyText}");
            } else {
                error_log("未匹配到规则且AI已关闭，不回复");
                $replyText = '';
            }
        }
    }

    $shouldReply = $autoOn && $replyText !== '';
    $replyMsgId = null;

    if ($shouldReply) {
        $stmt2 = $pdo->prepare("
            INSERT INTO messages (wx_user_id, wx_nickname, direction, content, is_ai_reply, rule_id, created_at)
            VALUES (:uid, :nick, 'out', :content, :is_ai, :rule_id, NOW())
        ");
        $stmt2->execute([
            ':uid' => $wxUserId,
            ':nick' => $wxNickname,
            ':content' => $replyText,
            ':is_ai' => 1,
            ':rule_id' => $usedRuleId,
        ]);
        $replyMsgId = (int)$pdo->lastInsertId();
    }

    $pdo->commit();

    json_response([
        'success' => true,
        'should_reply' => $shouldReply,
        'reply_text' => $replyText,
        'in_message_id' => $inMsgId,
        'reply_message_id' => $replyMsgId,
    ]);
} catch (Throwable $e) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    json_response(['error' => 'server_error', 'message' => $e->getMessage()], 500);
}


