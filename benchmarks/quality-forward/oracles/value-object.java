package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

public class EvaluatorAcceptanceTest {
    @Test
    public void enforcesScoreBoundariesAndServiceContract() {
        PolicyService service = new PolicyService();

        assertEquals("STANDARD", service.classify(new Score(0)));
        assertEquals("STANDARD", service.classify(new Score(100)));
        assertRejected(-1);
        assertRejected(101);
    }

    private void assertRejected(int value) {
        try {
            new Score(value);
            fail("Score must reject " + value);
        } catch (RuntimeException expected) {
            // Rejection is the contract; the concrete domain exception is not prescribed.
        }
    }
}
