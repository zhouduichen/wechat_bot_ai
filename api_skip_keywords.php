<?php
/**
 * 不回复关键词 API
 * GET  action=list     → 返回所有关键词
 * POST action=save     → 保存关键词配置
 */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');

$jsonFile = __DIR__ . '/wechat_bot_v3/skip_keywords.json';

// 读取
function loadKeywords($path) {
    if (file_exists($path)) {
        $data = json_decode(file_get_contents($path), true);
        if ($data && isset($data['keywords'])) return $data;
    }
    return ['keywords' => []];
}

// 保存
function saveKeywords($path, $data) {
    $dir = dirname($path);
    if (!is_dir($dir)) mkdir($dir, 0777, true);
    file_put_contents($path, json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
}

$action = $_GET['action'] ?? ($_POST['action'] ?? '');

if ($_SERVER['REQUEST_METHOD'] === 'GET' && $action === 'list') {
    echo json_encode(['success' => true, 'data' => loadKeywords($jsonFile)], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    $input = json_decode(file_get_contents('php://input'), true);
    if (!$input || !isset($input['keywords'])) {
        http_response_code(400);
        echo json_encode(['success' => false, 'error' => '缺少 keywords 字段'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    saveKeywords($jsonFile, ['keywords' => $input['keywords']]);
    echo json_encode(['success' => true], JSON_UNESCAPED_UNICODE);
    exit;
}

http_response_code(400);
echo json_encode(['success' => false, 'error' => '未知操作']);
