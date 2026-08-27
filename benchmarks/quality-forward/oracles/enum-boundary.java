package benchmark;

import org.junit.Test;

import static org.junit.Assert.assertSame;

public class EvaluatorAcceptanceTest {
    @Test
    public void returnsTheStrongClassificationType() {
        PolicyService service = new PolicyService();

        assertSame(PolicyClassification.INVALID, service.classify(-1));
        assertSame(PolicyClassification.STANDARD, service.classify(0));
    }
}
