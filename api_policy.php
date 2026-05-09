<?php
/**
 * 回复策略 API — 读写 reply_policy.json
 * GET  ?action=get              → 返回当前策略
 * POST ?action=save             → 保存整个策略（JSON body）
 * POST ?action=add&list=white   → 添加联系人到白名单 {name: "xxx"}
 * POST ?action=remove&list=white→ 从白名单移除 {name: "xxx"}
 * POST ?action=set_default      → 设置默认模式 {default: "skip"}
 */

require_once __DIR__ . '/config.php';

$policyFile = __DIR__ . '/wechat_bot_v3/reply_policy.json';

function loadPolicy() {
    global $policyFile;
    if (!file_exists($policyFile)) {
        $def = ['default' => 'ask', 'always_reply' => [], 'never_reply' => [], 'contact_overrides' => new stdClass()];
        file_put_contents($policyFile, json_encode($def, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
        return $def;
    }
    return json_decode(file_get_contents($policyFile), true);
}

function savePolicy($data) {
    global $policyFile;
    file_put_contents($policyFile, json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
}

$action = $_GET['action'] ?? $_POST['action'] ?? 'get';
$raw = file_get_contents('php://input');
$body = $raw ? json_decode($raw, true) : $_POST;

try {
    switch ($action) {
        case 'get':
            json_response(['success' => true, 'data' => loadPolicy()]);

        case 'save':
            if (!is_array($body)) {
                json_response(['success' => false, 'message' => '无效的JSON数据']);
            }
            // 保留结构
            $policy = loadPolicy();
            $policy['default'] = $body['default'] ?? $policy['default'];
            $policy['always_reply'] = $body['always_reply'] ?? $policy['always_reply'];
            $policy['never_reply'] = $body['never_reply'] ?? $policy['never_reply'];
            $policy['contact_overrides'] = $body['contact_overrides'] ?? $policy['contact_overrides'];
            savePolicy($policy);
            json_response(['success' => true, 'data' => $policy]);

        case 'set_default':
            $mode = $body['default'] ?? '';
            if (!in_array($mode, ['reply', 'skip', 'ask'])) {
                json_response(['success' => false, 'message' => '无效模式，可选: reply, skip, ask']);
            }
            $policy = loadPolicy();
            $policy['default'] = $mode;
            savePolicy($policy);
            json_response(['success' => true, 'data' => $policy]);

        case 'add':
            $listType = ($body['list'] ?? 'white') === 'black' ? 'never_reply' : 'always_reply';
            $name = trim($body['name'] ?? '');
            if ($name === '') {
                json_response(['success' => false, 'message' => '名字不能为空']);
            }
            $policy = loadPolicy();
            if (!in_array($name, $policy[$listType])) {
                $policy[$listType][] = $name;
                savePolicy($policy);
            }
            json_response(['success' => true, 'data' => $policy]);

        case 'remove':
            $listType = ($body['list'] ?? 'white') === 'black' ? 'never_reply' : 'always_reply';
            $name = trim($body['name'] ?? '');
            if ($name === '') {
                json_response(['success' => false, 'message' => '名字不能为空']);
            }
            $policy = loadPolicy();
            $policy[$listType] = array_values(array_filter($policy[$listType], function($n) use ($name) { return $n !== $name; }));
            savePolicy($policy);
            json_response(['success' => true, 'data' => $policy]);

        default:
            json_response(['success' => false, 'message' => '未知操作']);
    }
} catch (Throwable $e) {
    json_response(['success' => false, 'message' => $e->getMessage()]);
}
