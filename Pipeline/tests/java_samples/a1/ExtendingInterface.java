package org.example.geom;

public interface ExtendingInterface extends Shape, Comparable<ExtendingInterface> {
    double perimeter();
}
