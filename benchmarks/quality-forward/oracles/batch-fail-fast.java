package benchmark;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

public class EvaluatorAcceptanceTest {
    @Test
    public void preservesOrderAndInputWithoutReturningPartialResults() {
        PolicyService service = new PolicyService();
        List<Integer> input = new ArrayList<>(Arrays.asList(0, -1));

        assertEquals(
            Arrays.asList("STANDARD", "INVALID"),
            service.classifyAll(input)
        );
        assertEquals(Arrays.asList(0, -1), input);

        try {
            service.classifyAll(Arrays.asList(0, null, -1));
            fail("null elements must fail fast");
        } catch (InvalidScoreException expected) {
            // Exact exception type is part of the batch contract.
        }
    }
}
