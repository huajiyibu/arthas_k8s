
给pod中注入arthas工具，并可以通过常见命令进行展示，两类API

1. 注入arthas

入参：区域，集群，账户，命名空间，pod（pod是个列表）, 拷贝路径（默认 /tmp/arthas）
输出：注入成功（将arthas文件夹copy到pod的/tmp/arthas中），并成功启动(java -jar arthas-agent.jar, 然后根据提示输入 1)

2. 常用命令API

# （1） 查看大于 xxx 秒的请求路径
watch org.apache.catalina.core.ApplicationFilterChain doFilter \
'{params[0].getRequestURI(), params[1].getStatus()}' -x 2 '#cost>xxx'


# （2） 根据（1）的输出查看该请求路径对应的类方法
watch org.springframework.web.servlet.DispatcherServlet doDispatch '{
  #uri = params[0].getRequestURI(),
  #chain = target.getHandler(params[0]),
  #handler = #chain != null ? #chain.getHandler() : null,
  #handlerClass = #handler != null ? #handler.getClass().getName() : "null",
  #methodName = (#handler instanceof org.springframework.web.method.HandlerMethod) ? #handler.getMethod().getName() : "N/A",
  new String[]{#uri, #handlerClass, #methodName}
}'  'params[0].getRequestURI().equals("/api/loop")'  -n 5 --skipJDKMethod false


# （3）根据（2）输出的类和方法，查询时延方法查看调用栈，函数内部各函数花费时间
trace rest.example.rest.controller.UserController loop -n 5 '#cost>1000' --skipJDKMethod false

# （4）根据（2）输出的类和方法，输出统计值
monitor -c 10 rest.example.rest.controller.UserController * | grep -v timestamp | sort -k3 -nr | head -n 5