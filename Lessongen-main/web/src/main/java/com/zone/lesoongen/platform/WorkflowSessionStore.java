package com.zone.lesoongen.platform;


import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;


@Component
public class WorkflowSessionStore {


    private final Map<String,String> store =
            new ConcurrentHashMap<>();



    public void save(
            String lessonId,
            String sessionId
    ){

        store.put(
                lessonId,
                sessionId
        );

    }



    public String get(
            String lessonId
    ){

        return store.get(lessonId);

    }


}