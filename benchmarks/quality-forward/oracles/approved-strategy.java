package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class EvaluatorAcceptanceTest {
    @Test
    public void delegatesToBothApprovedStrategies() {
        PolicyService strict = new PolicyService(new StrictClassificationPolicy());
        PolicyService lenient = new PolicyService(new LenientClassificationPolicy());

        assertEquals("INVALID", strict.classify(-1));
        assertEquals("STANDARD", strict.classify(0));
        assertEquals("STANDARD", lenient.classify(-1));
        assertEquals("STANDARD", lenient.classify(0));
    }
}
