package benchmark;

import java.util.Optional;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;

public class EvaluatorAcceptanceTest {
    @Test
    public void representsQueryAbsenceExplicitly() {
        PolicyService service = new PolicyService();

        assertFalse(service.findClassification(-1).isPresent());
        assertEquals(Optional.of("STANDARD"), service.findClassification(0));
    }
}
