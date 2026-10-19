// 电商高并发链路：用户购物车与结算查询接口负载压测
// 测试目标：模拟用户结算峰值查询，测试服务网关高负载下的限流与容错指标

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");

export const options = {
  vus: 15,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(90)<500"], // 90% 请求在 500ms 内
    errors: ["rate<0.05"],             // 错误率低于 5%
  },
};

export default function () {
  const res = http.get("https://httpbin.org/get?scene=checkout&source=app");

  const success = check(res, {
    "status is 200": (r) => r.status === 200,
    "response time < 1000ms": (r) => r.timings.duration < 1000,
  });

  errorRate.add(!success);
  sleep(1);
}
