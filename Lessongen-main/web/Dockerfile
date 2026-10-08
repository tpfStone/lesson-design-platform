FROM eclipse-temurin:17-jdk AS build

WORKDIR /app
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
COPY src/ src/
RUN chmod +x ./mvnw && ./mvnw -B -ntp -DskipTests package

FROM eclipse-temurin:17-jre
ARG LESSONGEN_BUILD_COMMIT=unknown
ARG LESSONGEN_BUILD_DIRTY=unknown
WORKDIR /app
ENV LESSONGEN_BUILD_COMMIT=$LESSONGEN_BUILD_COMMIT \
    LESSONGEN_BUILD_DIRTY=$LESSONGEN_BUILD_DIRTY \
    LESSONGEN_RUNTIME_KIND=container
LABEL org.opencontainers.image.revision=$LESSONGEN_BUILD_COMMIT
COPY --from=build /app/target/Lesoongen-*.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
