package com.zone.lesoongen.platform;


import org.springframework.web.bind.annotation.*;

import java.util.Map;


@RestController
@RequestMapping("/api/platform/workflows")
public class WorkflowSessionController {


    private final WorkflowSessionService service;

    private final WorkflowSessionStore store;



    public WorkflowSessionController(
            WorkflowSessionService service,
            WorkflowSessionStore store
    ){

        this.service = service;
        this.store = store;

    }



    @PostMapping("/session")
    public Map create(
            @RequestBody Map body
    ){


        String subject =
                String.valueOf(body.get("subject"));


        String grade =
                String.valueOf(body.get("grade"));


        String topic =
                String.valueOf(body.get("topic"));


        String content =
                String.valueOf(body.get("content"));



        Map result =
                service.createSession(
                        subject,
                        grade,
                        topic,
                        content
                );



        Map session =
                (Map) result.get("session");


        String sessionId =
                String.valueOf(
                        session.get("id")
                );



        // 暂时保存F4 session
        store.save(
                "demo",
                sessionId
        );



        result.put(
                "native_session_id",
                sessionId
        );


        return result;

    }

}