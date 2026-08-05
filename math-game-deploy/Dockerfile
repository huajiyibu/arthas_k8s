# 构建一个包含 math-game.jar 的 Java 运行镜像
# 注意：Docker Hub 已废弃 openjdk 官方镜像，改用仍在维护的 eclipse-temurin
# 用 eclipse-temurin:8（JDK 版）而不是 -jre，因为后续注入 Arthas 需要 JDK 的 attach 能力
FROM eclipse-temurin:8
WORKDIR /app
COPY math-game.jar /app/math-game.jar
CMD ["java", "-jar", "math-game.jar"]
