package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

public class EvaluatorAcceptanceTest {
    @Test
    public void validatesAndAppliesTheRequiredThreshold() {
        PolicyService service = new PolicyService(100);

        assertEquals("STANDARD", service.classify(100));
        assertEquals("PREMIUM", service.classify(101));

        try {
            new PolicyService(0);
            fail("thresholds below one must be rejected");
        } catch (RuntimeException expected) {
            // Rejection is required; the concrete configuration exception is not prescribed.
        }
    }
}
