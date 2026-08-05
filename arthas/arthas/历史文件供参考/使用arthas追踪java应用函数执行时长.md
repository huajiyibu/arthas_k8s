
【用户故事(UserStory)
针对业务java程序，并且没有注入的场景下，可以在不重启业务服务的情况下，追踪java应用函数执行时长方便快速定位问题
【验收标准】
通过指定实例名称，pod名称直接将arthas注入到pod中

Arthas 是一款线上监控诊断产品，通过全局视角实时查看应用 load、内存、gc、线程的状态信息，并能在不修改应用代码的情况下，对业务问题进行诊断，包括查看方法调用的出入参、异常，监测方法执行耗时，类加载信息等，大大提升线上问题排查效率。

摘自: https://arthas.aliyun.com/doc/

---
# 下载
下载页面
https://github.com/alibaba/arthas/releases
下载链接
https://github.com/alibaba/arthas/releases/download/arthas-all-4.0.4/arthas-bin.zip

---
# 简单使用
将下载的zip包拷贝到容器中, 可以使用 `kubectl cp` 命令, 或者直接在pod所在主机上找到容器文件系统对应的主机目录位置,直接拷贝  
然后进入到容器中运行

```shell
java -jar arthas-boot.jar
```

然后会提示选择应用进程：

```
java -jar arthas-boot.jar
[INFO] JAVA_HOME: /root/jdk1.8.0_202/jre
[INFO] arthas-boot version: 4.0.4
[INFO] Found existing java process, please choose one and input the serial number of the process, eg : 1. Then hit ENTER.
* [1]: 7 org.apache.catalina.startup.Bootstrap
```

找到进程对应的index, 例如上图只有1个进程,则输入1,在输入回车/enter。  
Arthas 会 attach 到目标进程上，并进入到 交互模式

在交互模式下使用 trace 命令来追踪指定类的方法耗时

```shell
trace cn.chinaunicom.mysqlpool.SqlHandleServlet getDbHandle --skipJDKMethod false
Press Q or Ctrl+C to abort.
Affect(class count: 1 , method count: 1) cost in 32 ms, listenerId: 6
`---ts=2024-11-25 15:17:17.442;thread_name=http-nio-8080-exec-9;id=124;is_daemon=true;priority=5;TCCL=org.apache.catalina.loader.ParallelWebappClassLoader@30312470
    `---[0.242793ms] cn.chinaunicom.mysqlpool.SqlHandleServlet:getDbHandle()
        +---[41.98% 0.10193ms ] cn.chinaunicom.servicehandle.utility.BaseHttpServlet:createDbPool() #26
        +---[7.60% 0.018453ms ] cn.chinaunicom.mysqlpool.SqlHandleServlet:createDbHandleInterface() #27
        `---[5.47% 0.013291ms ] cn.chinaunicom.databaseaccess.DbHandleAbs:setDbHandleInterface() #27

`---ts=2024-11-25 15:18:22.967;thread_name=http-nio-8080-exec-6;id=121;is_daemon=true;priority=5;TCCL=org.apache.catalina.loader.ParallelWebappClassLoader@30312470
    `---[0.161529ms] cn.chinaunicom.mysqlpool.SqlHandleServlet:getDbHandle()
        +---[45.87% 0.074099ms ] cn.chinaunicom.servicehandle.utility.BaseHttpServlet:createDbPool() #26
        +---[6.36% 0.010278ms ] cn.chinaunicom.mysqlpool.SqlHandleServlet:createDbHandleInterface() #27
        `---[3.24% 0.005234ms ] cn.chinaunicom.databaseaccess.DbHandleAbs:setDbHandleInterface() #27

```

根据输出信息, 可以看到函数执行耗时, 以及函数内调用的其他函数调用次数和耗时,   
然后一级级的查询下去,可以最终看到函数主要耗时在哪个函数上, 并分析原因  

**一些参数说明** :  
- `--skipJDKMethod false` : 默认情况下，trace 不会包含 jdk 里的函数调用，如果希望 trace jdk 里的函数，需要显式设置 `--skipJDKMethod false`   
- `-m 150` 指定 Class 匹配的最大数量,建议加上, 例如可以使用 `trace * * -m 10000` 追踪所有方法  
- `'#cost > 10'` : 只会展示耗时大于 10ms 的调用路径，有助于在排查问题的时候，只关注异常情况


---
# 其他

## trace 追踪的类和方法名称需要应用提供
目前没有看到从头开始抓取所有类的方法, 需要应用提供需要抓取的类和方法名称  

## 更多的命令和参数可以参考官方文档
https://arthas.aliyun.com/doc/





