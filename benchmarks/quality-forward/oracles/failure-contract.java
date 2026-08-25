package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

public class EvaluatorAcceptanceTest {
    @Test
    public void rejectsNegativeScoresWithTheDomainException() throws Exception {
        PolicyService service = new PolicyService();

        assertEquals("STANDARD", service.classify(0));
        try {
            service.classify(-1);
            fail("negative scores must fail");
        } catch (InvalidScoreException expected) {
            // Exact exception type is the published failure contract.
        }
    }
}
