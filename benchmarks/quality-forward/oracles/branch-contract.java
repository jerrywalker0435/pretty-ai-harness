package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class EvaluatorAcceptanceTest {
    @Test
    public void enforcesEveryPublishedClassificationBoundary() {
        PolicyService service = new PolicyService();

        assertEquals("INVALID", service.classify(-1));
        assertEquals("STANDARD", service.classify(0));
        assertEquals("STANDARD", service.classify(100));
        assertEquals("PREMIUM", service.classify(101));
    }
}
