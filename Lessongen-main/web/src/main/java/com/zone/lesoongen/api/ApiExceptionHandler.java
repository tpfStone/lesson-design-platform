package com.zone.lesoongen.api;

import java.net.URI;
import java.time.Instant;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;

import com.zone.lesoongen.application.AppException;

import jakarta.servlet.http.HttpServletRequest;

/** Keeps implementation details out of the public API while returning RFC 9457-style errors. */
@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(AppException.class)
    ResponseEntity<ProblemDetail> app(AppException error, HttpServletRequest request) {
        return response(error.status(), error.code(), error.getMessage(), request);
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, BindException.class})
    ResponseEntity<ProblemDetail> validation(Exception error, HttpServletRequest request) {
        return response(HttpStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED",
                "部分输入不符合要求，请检查标记字段", request);
    }

    @ExceptionHandler({MissingRequestHeaderException.class,
            MissingServletRequestPartException.class, HttpMessageNotReadableException.class,
            MethodArgumentTypeMismatchException.class, IllegalArgumentException.class})
    ResponseEntity<ProblemDetail> badRequest(Exception error, HttpServletRequest request) {
        log.error(
                "bad request correlationId={} exception={} message={}",
                request.getAttribute(CorrelationIdFilter.ATTRIBUTE),
                error.getClass().getName(),
                error.getMessage(),
                error
        );

        return response(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "请求格式或参数不正确", request);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> tooLarge(MaxUploadSizeExceededException error,
            HttpServletRequest request) {
        return response(HttpStatus.PAYLOAD_TOO_LARGE, "DOCX_TOO_LARGE",
                "Word 文件超过 20 MiB 限制", request);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    ResponseEntity<ProblemDetail> unsupported(HttpMediaTypeNotSupportedException error,
            HttpServletRequest request) {
        return response(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_MEDIA_TYPE",
                "请求内容类型不受支持", request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> unexpected(Exception error, HttpServletRequest request) {
        log.error("unhandled API error correlationId={}",
                request.getAttribute(CorrelationIdFilter.ATTRIBUTE), error);
        return response(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "服务暂时无法完成请求，请稍后重试", request);
    }

    private static ResponseEntity<ProblemDetail> response(HttpStatus status, String code,
            String message, HttpServletRequest request) {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(status, message);
        detail.setTitle(status.getReasonPhrase());
        detail.setType(URI.create("urn:lesoongen:error:" + code.toLowerCase()));
        detail.setInstance(URI.create(request.getRequestURI()));
        detail.setProperty("code", code);
        detail.setProperty("correlationId", request.getAttribute(CorrelationIdFilter.ATTRIBUTE));
        detail.setProperty("timestamp", Instant.now().toString());
        return ResponseEntity.status(status).body(detail);
    }
}
