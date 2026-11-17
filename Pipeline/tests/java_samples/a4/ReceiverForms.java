package org.example.game;

import java.util.ArrayList;
import java.util.List;

public class ReceiverForms {
    private List<String> names = new ArrayList<String>();
    private ReceiverForms next;
    private ReceiverForms[] all = new ReceiverForms[2];

    public ReceiverForms self() {
        return this;
    }

    public int size() {
        return names.size();
    }

    public void forms(ReceiverForms other) {
        other.size();
        this.names.clear();
        other.next.size();
        System.out.println("x");
        self().size();
        all[0].size();
        (other).size();
        new ReceiverForms().size();
        "abc".length();
        size();
        this.size();
        super.toString();
        all[1].next.size();
        super.hashCode();
    }
}
