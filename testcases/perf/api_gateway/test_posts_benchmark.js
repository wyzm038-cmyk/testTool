// JSONPlaceholder API 网关吞吐量与高并发压测
// 测试目标：GET /posts 核心数据接口高并发吞吐量与 P95 分位数

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");

export const options = {
  vus: 20,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<600"], // 95% 请求在 600ms 内
    errors: ["rate<0.1"],             // 错误率低于 10%
  },
};

export default function () {
  const host = __ENV.TARGET_HOST || "https://jsonplaceholder.typicode.com";
  const res = http.get(`${host}/posts`);

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
    "response time < 800ms": (r) => r.timings.duration < 800,
    "body is array": (r) => Array.isArray(JSON.parse(r.body)),
  });

  errorRate.add(!success);
  sleep(1);
}
