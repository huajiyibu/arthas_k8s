package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 演示控制器：提供两个接口。
 *  - /fast : 正常接口，秒回
 *  - /slow : 慢接口，故意睡 2 秒（用来让"慢接口查询"接口1 抓到）
 */
@RestController
public class DemoController {

    @GetMapping("/fast")
    public String fast() {
        return "fast ok";
    }

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(2000);   // 故意慢 2 秒
        return "slow ok";
    }
}
