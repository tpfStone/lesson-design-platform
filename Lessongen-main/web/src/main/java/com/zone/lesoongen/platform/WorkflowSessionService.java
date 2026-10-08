package com.zone.lesoongen.platform;


import org.springframework.stereotype.Service;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

import java.util.Map;
import java.util.UUID;


@Service
public class WorkflowSessionService {


    private final RestTemplate restTemplate = new RestTemplate();


    public Map createSession(
            String subject,
            String grade,
            String topic,
            String content
    ) {


        Map metadata = Map.of(
                "subject", subject,
                "grade", grade,
                "topic", topic
        );


        Map body = Map.of(
                "request_key",
                UUID.randomUUID().toString(),

                "metadata",
                metadata,

                "content",
                content
        );


        System.out.println("======================");
        System.out.println("F4 BODY:");
        System.out.println(body);
        System.out.println("======================");


        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);


        HttpEntity<Map> request =
                new HttpEntity<>(body, headers);



        ResponseEntity<Map> response =
                restTemplate.postForEntity(
                        "http://127.0.0.1:8000/api/sessions",
                        request,
                        Map.class
                );


        return response.getBody();

    }

}