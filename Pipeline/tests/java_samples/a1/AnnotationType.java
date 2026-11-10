package org.example.game;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

/**
 * Marks a game option.
 */
@Retention(RetentionPolicy.RUNTIME)
public @interface AnnotationType {
    String name() default "";

    int order() default 0;
}
