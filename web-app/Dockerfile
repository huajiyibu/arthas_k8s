# Web 应用运行镜像：把 Spring Boot 打好的 jar 装进 Java 运行环境
# 用 JDK 版（eclipse-temurin:8），因为后续要注入 Arthas（需要 attach 能力）
FROM eclipse-temurin:8
WORKDIR /app
COPY target/demo-web-1.0.0.jar /app/app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
