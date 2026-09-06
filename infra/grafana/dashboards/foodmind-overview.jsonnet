// Grafana dashboard source. Render it with `make grafana-dashboards`.
// Rows are collapsed by default so operators can expand the concern they need.
local target(expression, legend, refId='A') = {
  expr: expression,
  legendFormat: legend,
  refId: refId,
};

local panel(id, title, expression, legend, x, y, unit='short', w=12, h=8) = {
  id: id,
  title: title,
  type: 'timeseries',
  datasource: { type: 'prometheus', uid: 'prometheus' },
  gridPos: { h: h, w: w, x: x, y: y },
  fieldConfig: { defaults: { unit: unit }, overrides: [] },
  options: {
    legend: { displayMode: 'table', placement: 'bottom', showLegend: true },
    tooltip: { mode: 'multi', sort: 'desc' },
  },
  targets: [target(expression, legend)],
};

local row(id, title, panels, y) = {
  id: id,
  title: title,
  type: 'row',
  collapsed: true,
  gridPos: { h: 1, w: 24, x: 0, y: y },
  panels: panels,
};

{
  annotations: { list: [] },
  editable: true,
  graphTooltip: 1,
  links: [
    {
      title: 'Explore FoodMind traces',
      type: 'link',
      url: '/explore?left={"datasource":"tempo"}',
    },
  ],
  panels: [
    row(100, 'API', [
      panel(1, 'Request rate', 'sum by (method, path, status) (rate(foodmind_api_requests_total{path!="/unmatched"}[$__rate_interval]))', '{{method}} {{path}} · {{status}}', 0, 0, 'reqps'),
      panel(2, 'Request latency p95', 'histogram_quantile(0.95, sum by (le, method, path) (rate(foodmind_api_request_duration_seconds_bucket{path!="/unmatched"}[$__rate_interval])))', '{{method}} {{path}}', 12, 0, 's'),
      panel(3, 'Server-error ratio', 'sum(rate(foodmind_api_requests_total{path!="/unmatched",status=~"5.."}[$__rate_interval])) / clamp_min(sum(rate(foodmind_api_requests_total{path!="/unmatched"}[$__rate_interval])), 0.001)', '5xx ratio', 0, 8, 'percentunit'),
      panel(4, 'Requests in progress', 'sum by (method) (foodmind_api_requests_in_progress)', '{{method}}', 12, 8, 'short'),
    ], 0),

    row(200, 'Orchestrator', [
      panel(5, 'Run rate', 'sum by (route, outcome) (rate(foodmind_orchestrator_runs_total[$__rate_interval]))', '{{route}} · {{outcome}}', 0, 0, 'ops'),
      panel(6, 'End-to-end latency p95', 'histogram_quantile(0.95, sum by (le, route, outcome) (rate(foodmind_orchestrator_duration_seconds_bucket[$__rate_interval])))', '{{route}} · {{outcome}}', 12, 0, 's'),
      panel(7, 'Stage latency p95', 'histogram_quantile(0.95, sum by (le, stage, outcome) (rate(foodmind_orchestrator_stage_duration_seconds_bucket[$__rate_interval])))', '{{stage}} · {{outcome}}', 0, 8, 's'),
      panel(8, 'Failed-run rate', 'sum by (route) (rate(foodmind_orchestrator_runs_total{outcome="error"}[$__rate_interval]))', '{{route}}', 12, 8, 'ops'),
    ], 1),

    row(300, 'Agents and retrieval', [
      panel(9, 'Specialist-agent executions', 'sum by (agent, outcome, cached) (rate(foodmind_agent_runs_total[$__rate_interval]))', '{{agent}} · {{outcome}} · cache={{cached}}', 0, 0, 'ops'),
      panel(10, 'Specialist-agent latency p95', 'histogram_quantile(0.95, sum by (le, agent, outcome) (rate(foodmind_agent_duration_seconds_bucket{cached="false"}[$__rate_interval])))', '{{agent}} · {{outcome}}', 12, 0, 's'),
      panel(11, 'Tool calls', 'sum by (agent, tool, outcome) (rate(foodmind_tool_calls_total[$__rate_interval]))', '{{agent}} · {{tool}} · {{outcome}}', 0, 8, 'ops'),
      panel(12, 'Retrieval operations', 'sum by (operation, outcome, cache) (rate(foodmind_retrieval_operations_total[$__rate_interval]))', '{{operation}} · {{outcome}} · cache={{cache}}', 12, 8, 'ops'),
      panel(13, 'Retrieval latency p95', 'histogram_quantile(0.95, sum by (le, operation, outcome, cache) (rate(foodmind_retrieval_duration_seconds_bucket[$__rate_interval])))', '{{operation}} · {{outcome}} · cache={{cache}}', 0, 16, 's'),
      panel(14, 'Agent cache-hit rate', 'sum(rate(foodmind_agent_runs_total{cached="true",outcome="success"}[$__rate_interval])) / clamp_min(sum(rate(foodmind_agent_runs_total{outcome="success"}[$__rate_interval])), 0.001)', 'cache-hit rate', 12, 16, 'percentunit'),
    ], 2),

    row(400, 'NATS', [
      panel(15, 'Chat commands published', 'sum by (outcome) (rate(foodmind_nats_commands_total[$__rate_interval]))', '{{outcome}}', 0, 0, 'ops'),
      panel(16, 'Command publish latency p95', 'histogram_quantile(0.95, sum by (le, outcome) (rate(foodmind_nats_command_duration_seconds_bucket[$__rate_interval])))', '{{outcome}}', 12, 0, 's'),
      panel(17, 'Execution-event flow', 'sum by (direction, event, outcome) (rate(foodmind_nats_events_total[$__rate_interval]))', '{{direction}} · {{event}} · {{outcome}}', 0, 8, 'ops'),
      panel(18, 'Active SSE streams', 'sum(foodmind_nats_active_streams)', 'active streams', 12, 8, 'short'),
    ], 3),

    row(500, 'Chat worker', [
      panel(19, 'Commands handled', 'sum by (outcome) (rate(foodmind_chat_worker_commands_total[$__rate_interval]))', '{{outcome}}', 0, 0, 'ops'),
      panel(20, 'Worker command latency p95', 'histogram_quantile(0.95, sum by (le, outcome) (rate(foodmind_chat_worker_command_duration_seconds_bucket[$__rate_interval])))', '{{outcome}}', 12, 0, 's'),
      panel(21, 'Commands in progress', 'sum(foodmind_chat_worker_commands_in_progress)', 'commands in progress', 0, 8, 'short'),
      panel(22, 'Message persistence latency p95', 'histogram_quantile(0.95, sum by (le, step, outcome) (rate(foodmind_message_processing_step_duration_seconds_bucket[$__rate_interval])))', '{{step}} · {{outcome}}', 12, 8, 's'),
    ], 4),

    row(600, 'LLM token usage', [
      panel(23, 'Token use by model', 'sum by (component, agent, model, direction) (increase(foodmind_llm_tokens_total[$__rate_interval]))', '{{component}} · {{agent}} · {{model}} · {{direction}}', 0, 0, 'tokens'),
      panel(24, 'Total input and output tokens', 'sum by (direction) (increase(foodmind_llm_tokens_total[$__rate_interval]))', '{{direction}}', 12, 0, 'tokens'),
      panel(25, 'LLM run outcomes', 'sum by (component, agent, model, outcome) (rate(foodmind_llm_requests_total[$__rate_interval]))', '{{component}} · {{agent}} · {{model}} · {{outcome}}', 0, 8, 'ops'),
      panel(26, 'LLM error ratio', 'sum(rate(foodmind_llm_requests_total{outcome="error"}[$__rate_interval])) / clamp_min(sum(rate(foodmind_llm_requests_total[$__rate_interval])), 0.001)', 'error ratio', 12, 8, 'percentunit'),
    ], 5),

    row(700, 'Feedback', [
      panel(27, 'Feedback submissions', 'sum by (is_useful) (increase(foodmind_feedback_submissions_total[$__rate_interval]))', 'useful={{is_useful}}', 0, 0, 'short'),
      panel(28, 'Useful-feedback ratio', 'sum(increase(foodmind_feedback_submissions_total{is_useful="true"}[$__rate_interval])) / clamp_min(sum(increase(foodmind_feedback_submissions_total[$__rate_interval])), 1)', 'useful feedback ratio', 12, 0, 'percentunit'),
    ], 6),

    row(750, 'Conversation context', [
      panel(33, 'Context-building latency p95', 'histogram_quantile(0.95, sum by (le, step, outcome) (rate(foodmind_message_processing_step_duration_seconds_bucket{step=~"load_conversation|load_history|build_context"}[$__rate_interval])))', '{{step}} · {{outcome}}', 0, 0, 's'),
      panel(34, 'Context messages p95', 'histogram_quantile(0.95, sum by (le) (rate(foodmind_conversation_context_messages_bucket[$__rate_interval])))', 'messages', 12, 0, 'short'),
      panel(35, 'Context characters p95', 'histogram_quantile(0.95, sum by (le) (rate(foodmind_conversation_context_characters_bucket[$__rate_interval])))', 'characters', 0, 8, 'short'),
      panel(36, 'Message-processing steps', 'sum by (step, outcome) (rate(foodmind_message_processing_step_duration_seconds_count[$__rate_interval]))', '{{step}} · {{outcome}}', 12, 8, 'ops'),
    ], 7),

    row(800, 'Platform health', [
      panel(29, 'Prometheus scrape health', 'up{job=~"foodmind-api|foodmind-chat-worker"}', '{{job}}', 0, 0, 'short'),
      panel(30, 'Process resident memory', 'sum by (job) (process_resident_memory_bytes{job=~"foodmind-api|foodmind-chat-worker"})', '{{job}}', 12, 0, 'bytes'),
      panel(31, 'Python process CPU', 'sum by (job) (rate(process_cpu_seconds_total{job=~"foodmind-api|foodmind-chat-worker"}[$__rate_interval]))', '{{job}}', 0, 8, 'percentunit'),
      panel(32, 'Python open file descriptors', 'sum by (job) (process_open_fds{job=~"foodmind-api|foodmind-chat-worker"})', '{{job}}', 12, 8, 'short'),
    ], 8),
  ],
  refresh: '30s',
  schemaVersion: 41,
  tags: ['foodmind', 'orchestrator', 'nats'],
  templating: { list: [] },
  time: { from: 'now-6h', to: 'now' },
  timezone: 'browser',
  title: 'FoodMind Operations',
  uid: 'foodmind-overview',
  version: 3,
}
