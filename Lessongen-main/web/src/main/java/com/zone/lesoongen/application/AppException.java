package com.zone.lesoongen.application;

import org.springframework.http.HttpStatus;

public class AppException extends RuntimeException {
    private final HttpStatus status;
    private final String code;

    public AppException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus status() { return status; }
    public String code() { return code; }

    public static AppException notFound(String resource) {
        return new AppException(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", resource + "不存在");
    }
}
