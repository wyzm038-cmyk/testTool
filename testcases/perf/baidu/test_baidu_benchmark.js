// 百度检索吞吐量与首页响应时间基准压测
// 测试目标：验证百度首页在并发高负载下的 HTTP 状态码与响应延时指标

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");

export const options = {
  vus: 10,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<800"], // 95% 请求在 800ms 内完成
    errors: ["rate<0.05"],             // 错误率低于 5%
  },
};

export default function () {
  const res = http.get("https://www.baidu.com");

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
    "response time < 1s": (r) => r.timings.duration < 1000,
    "page contains baidu": (r) => r.body && r.body.includes("baidu"),
  });

  errorRate.add(!success);
  sleep(1);
}
