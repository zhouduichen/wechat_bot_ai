<?php
// 简单规则配置接口：被 Web 后台用 Ajax 调用
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/ai_helper.php';

header('Content-Type: application/json; charset=utf-8');

$action = $_GET['action'] ?? $_POST['action'] ?? 'list';
$pdo = get_pdo();

try {
    switch ($action) {
        case 'list':
            $stmt = $pdo->query("SELECT * FROM auto_reply_rules ORDER BY id DESC");
            $rules = $stmt->fetchAll();
            json_response(['success' => true, 'data' => $rules]);
            break;

        case 'create':
            $keyword = trim((string)($_POST['keyword'] ?? ''));
            $matchType = $_POST['match_type'] ?? 'contain';
            $replyText = trim((string)($_POST['reply_text'] ?? ''));
            $isActive = (int)($_POST['is_active'] ?? 1);

            if ($keyword === '' || $replyText === '') {
                json_response(['success' => false, 'message' => '关键词和回复内容不能为空']);
            }

            if (!in_array($matchType, ['contain', 'equal'], true)) {
                $matchType = 'contain';
            }

            $stmt = $pdo->prepare("
                INSERT INTO auto_reply_rules(keyword, match_type, reply_text, is_active, created_at, updated_at)
                VALUES(:kw, :mt, :rt, :act, NOW(), NOW())
            ");
            $stmt->execute([
                ':kw' => $keyword,
                ':mt' => $matchType,
                ':rt' => $replyText,
                ':act' => $isActive,
            ]);
            json_response(['success' => true]);
            break;

        case 'toggle':
            $id = (int)($_POST['id'] ?? 0);
            $isActive = (int)($_POST['is_active'] ?? 0);
            if ($id <= 0) {
                json_response(['success' => false, 'message' => '参数错误']);
            }
            $stmt = $pdo->prepare("UPDATE auto_reply_rules SET is_active = :act, updated_at = NOW() WHERE id = :id");
            $stmt->execute([':act' => $isActive, ':id' => $id]);
            json_response(['success' => true]);
            break;

        case 'delete':
            $id = (int)($_POST['id'] ?? 0);
            if ($id <= 0) {
                json_response(['success' => false, 'message' => '参数错误']);
            }
            $stmt = $pdo->prepare("DELETE FROM auto_reply_rules WHERE id = :id");
            $stmt->execute([':id' => $id]);
            json_response(['success' => true]);
            break;

        case 'settings_get':
            $autoOn = get_setting('auto_reply_enabled', '1');
            $aiOn = get_setting('ai_enabled', '1');
            json_response(['success' => true, 'auto_reply_enabled' => $autoOn === '1', 'ai_enabled' => $aiOn === '1']);
            break;

        case 'settings_set':
            if (isset($_POST['auto_reply_enabled'])) {
                $v = $_POST['auto_reply_enabled'] === '1' ? '1' : '0';
                set_setting('auto_reply_enabled', $v);
            }
            if (isset($_POST['ai_enabled'])) {
                $v = $_POST['ai_enabled'] === '1' ? '1' : '0';
                set_setting('ai_enabled', $v);
            }
            json_response(['success' => true]);
            break;

        case 'messages_recent':
            $limit = max(1, min(100, (int)($_GET['limit'] ?? 50)));
            $stmt = $pdo->prepare("
                SELECT * FROM messages
                ORDER BY id DESC
                LIMIT :lim
            ");
            $stmt->bindValue(':lim', $limit, PDO::PARAM_INT);
            $stmt->execute();
            $rows = $stmt->fetchAll();
            json_response(['success' => true, 'data' => $rows]);
            break;

        default:
            json_response(['success' => false, 'message' => '未知操作']);
    }
} catch (Throwable $e) {
    json_response(['success' => false, 'message' => $e->getMessage()]);
}


