# Setting Up an EN16931 / PEPPOL Validator Service

This document describes three options for how to create a standalone EN16931 e-invoice validator, suitable for running as a Docker service.

## Option 1: Pre-built Docker Image (Easiest)

The [easybill/peppol-bis-billing-validator](https://github.com/easybill/peppol-bis-billing-validator) provides a ready-to-use Docker image that validates against PEPPOL BIS Billing 3.0 rules (which include EN16931).

### Quick Start

```bash
docker run -p 8080:8080 easybill/peppol-bis-billing-validator:latest
```

Or with docker-compose:

```yaml
# docker-compose.yml
version: '3'
services:
  validator:
    image: easybill/peppol-bis-billing-validator:latest
    ports:
      - "8080:8080"
    environment:
      - JAVA_OPTS=-Xmx512m
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### API Usage

```bash
# Validate an invoice
curl -X POST http://localhost:8080/validation \
  -H "Content-Type: application/xml" \
  -d @invoice.xml

# Health check
curl http://localhost:8080/health

# OpenAPI docs
curl http://localhost:8080/swagger
```

**Response**: HTTP 200 with SVRL report if valid, HTTP 400 with `svrl:failed-assert` elements if invalid.

### Limitations

- Only validates PEPPOL BIS Billing 3.0 (UBL invoices)
- Does not support CII format or other CIUS variants (XRechnung, Factur-X, etc.)


## Option 2: Build Your Own with PHIVE (More Comprehensive)

[PHIVE](https://github.com/phax/phive) (Philip Helger Integrative Validation Engine) with [phive-rules](https://github.com/phax/phive-rules) supports 30+ validation rule sets including:

- Pure EN16931 (CEN TC 434)
- PEPPOL BIS 3.0
- XRechnung (Germany)
- Factur-X / ZUGFeRD
- Country-specific CIUS (AT, IT, NL, etc.)

### Step 1: Create Maven Project

```xml
<!-- pom.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>en16931-validator</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
        <phive.version>10.0.3</phive.version>
        <phive-rules.version>3.2.1</phive-rules.version>
    </properties>

    <dependencies>
        <!-- PHIVE core -->
        <dependency>
            <groupId>com.helger.phive</groupId>
            <artifactId>phive-xml</artifactId>
            <version>${phive.version}</version>
        </dependency>

        <!-- EN16931 validation rules -->
        <dependency>
            <groupId>com.helger.phive.rules</groupId>
            <artifactId>phive-rules-en16931</artifactId>
            <version>${phive-rules.version}</version>
        </dependency>

        <!-- PEPPOL BIS rules (includes EN16931 + PEPPOL-specific) -->
        <dependency>
            <groupId>com.helger.phive.rules</groupId>
            <artifactId>phive-rules-peppol</artifactId>
            <version>${phive-rules.version}</version>
        </dependency>

        <!-- For REST API -->
        <dependency>
            <groupId>io.javalin</groupId>
            <artifactId>javalin</artifactId>
            <version>5.6.3</version>
        </dependency>

        <!-- JSON output -->
        <dependency>
            <groupId>com.google.code.gson</groupId>
            <artifactId>gson</artifactId>
            <version>2.10.1</version>
        </dependency>

        <!-- Logging -->
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.5.1</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>com.example.ValidatorService</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

### Step 2: Create Validator Service

```java
// src/main/java/com/example/ValidatorService.java
package com.example;

import com.helger.commons.io.stream.StringInputStream;
import com.helger.phive.api.execute.ValidationExecutionManager;
import com.helger.phive.api.executorset.IValidationExecutorSet;
import com.helger.phive.api.executorset.ValidationExecutorSetRegistry;
import com.helger.phive.api.result.ValidationResultList;
import com.helger.phive.api.result.ValidationResult;
import com.helger.phive.en16931.EN16931Validation;
import com.helger.phive.peppol.PeppolValidation;
import com.helger.phive.xml.source.ValidationSourceXML;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.nio.charset.StandardCharsets;
import java.util.*;

public class ValidatorService {

    private static final ValidationExecutorSetRegistry<?> REGISTRY = new ValidationExecutorSetRegistry<>();
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    static {
        // Register EN16931 rules (pure European standard)
        EN16931Validation.initEN16931(REGISTRY);

        // Register PEPPOL BIS rules (EN16931 + PEPPOL-specific)
        PeppolValidation.initPeppol(REGISTRY);
    }

    public static void main(String[] args) {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));

        Javalin app = Javalin.create().start(port);

        // Health check
        app.get("/health", ctx -> ctx.result("OK"));

        // List available validation profiles
        app.get("/profiles", ValidatorService::listProfiles);

        // Validate document
        app.post("/validate", ValidatorService::validateDocument);
        app.post("/validate/{profile}", ValidatorService::validateDocument);

        System.out.println("Validator service started on port " + port);
    }

    private static void listProfiles(Context ctx) {
        List<Map<String, String>> profiles = new ArrayList<>();
        REGISTRY.getAll().forEach(ves -> {
            Map<String, String> profile = new HashMap<>();
            profile.put("id", ves.getID().getAsSingleID());
            profile.put("name", ves.getDisplayName());
            profiles.add(profile);
        });
        ctx.contentType("application/json").result(GSON.toJson(profiles));
    }

    private static void validateDocument(Context ctx) {
        String xml = ctx.body();
        String profileId = ctx.pathParam("profile");

        // Default to PEPPOL BIS 3.0 Invoice if no profile specified
        if (profileId == null || profileId.isEmpty()) {
            profileId = "eu.peppol.bis3:invoice:2024.11";  // Update version as needed
        }

        // Find the validation executor set
        IValidationExecutorSet<?> ves = null;
        for (var v : REGISTRY.getAll()) {
            if (v.getID().getAsSingleID().equals(profileId) ||
                v.getID().getAsSingleID().contains(profileId)) {
                ves = v;
                break;
            }
        }

        if (ves == null) {
            ctx.status(400).json(Map.of(
                "error", "Unknown profile: " + profileId,
                "hint", "Use GET /profiles to list available profiles"
            ));
            return;
        }

        // Perform validation
        ValidationSourceXML source = ValidationSourceXML.create(
            null, new StringInputStream(xml, StandardCharsets.UTF_8)
        );

        ValidationResultList results = ValidationExecutionManager.executeValidation(ves, source);

        // Build response
        Map<String, Object> response = new HashMap<>();
        response.put("profile", ves.getID().getAsSingleID());
        response.put("valid", results.containsNoError());
        response.put("errorCount", results.getErrorCount());
        response.put("warningCount", results.getWarningCount());

        List<Map<String, String>> issues = new ArrayList<>();
        for (ValidationResult vr : results) {
            for (var item : vr.getErrorList()) {
                Map<String, String> issue = new HashMap<>();
                issue.put("level", item.getErrorLevel().getID());
                issue.put("id", item.getErrorID());
                issue.put("text", item.getErrorText(Locale.ENGLISH));
                issue.put("location", item.hasErrorLocation() ?
                    item.getErrorLocation().getAsString() : null);
                issues.add(issue);
            }
        }
        response.put("issues", issues);

        int status = results.containsNoError() ? 200 : 422;
        ctx.status(status).contentType("application/json").result(GSON.toJson(response));
    }
}
```

### Step 3: Build

```bash
mvn clean package
```

This creates `target/en16931-validator-1.0.0.jar` (fat JAR with all dependencies).

### Step 4: Create Dockerfile

```dockerfile
# Dockerfile
FROM eclipse-temurin:11-jre-alpine

WORKDIR /app
COPY target/en16931-validator-1.0.0.jar app.jar

ENV PORT=8080
ENV JAVA_OPTS="-Xmx512m"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -q --spider http://localhost:8080/health || exit 1

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

### Step 5: Build and Run Docker Image

```bash
# Build
docker build -t en16931-validator:latest .

# Run
docker run -p 8080:8080 en16931-validator:latest
```

### Step 6: API Usage

```bash
# List available validation profiles
curl http://localhost:8080/profiles | jq .

# Validate against default profile (PEPPOL BIS 3.0)
curl -X POST http://localhost:8080/validate \
  -H "Content-Type: application/xml" \
  -d @invoice.xml

# Validate against specific profile (pure EN16931 UBL)
curl -X POST http://localhost:8080/validate/en16931:ubl:1.3.11 \
  -H "Content-Type: application/xml" \
  -d @invoice.xml

# Validate against EN16931 CII
curl -X POST http://localhost:8080/validate/en16931:cii:1.3.11 \
  -H "Content-Type: application/xml" \
  -d @invoice.xml
```

### Example Response

```json
{
  "profile": "eu.peppol.bis3:invoice:2024.11",
  "valid": false,
  "errorCount": 2,
  "warningCount": 1,
  "issues": [
    {
      "level": "ERROR",
      "id": "BR-16",
      "text": "An Invoice shall have at least one Invoice line (BG-25).",
      "location": "/Invoice"
    },
    {
      "level": "WARN",
      "id": "UBL-SR-09",
      "text": "Seller tax registration identifier should be present.",
      "location": "/Invoice/AccountingSupplierParty"
    }
  ]
}
```


## Option 3: Use Official CEN Artefacts Directly

If you prefer using the official CEN TC 434 validation artefacts:

1. Download from [ConnectingEurope/eInvoicing-EN16931](https://github.com/ConnectingEurope/eInvoicing-EN16931/releases)
2. Use Saxon (XSLT 2.0 processor) to run the pre-compiled XSLT files

```bash
# Install Saxon
# On Ubuntu/Debian:
apt-get install libsaxonb-java

# Validate using pre-compiled XSLT
java -jar /usr/share/java/saxon.jar \
  -s:invoice.xml \
  -xsl:EN16931-UBL-validation.xslt \
  -o:validation-report.xml
```

The output is an SVRL (Schematron Validation Report Language) document.


## Comparison

| Feature | easybill Docker | Custom PHIVE | CEN XSLT |
|---------|-----------------|--------------|----------|
| Setup complexity | Very low | Medium | Low |
| PEPPOL BIS 3.0 | Yes | Yes | No |
| Pure EN16931 | Partial | Yes | Yes |
| XRechnung, Factur-X | No | Yes | No |
| CII format | No | Yes | Yes |
| JSON API | No (SVRL) | Yes | No (SVRL) |
| Customizable | No | Yes | Limited |


## References

- [phive - Validation Engine](https://github.com/phax/phive)
- [phive-rules - Validation Rules](https://github.com/phax/phive-rules)
- [easybill/peppol-bis-billing-validator](https://github.com/easybill/peppol-bis-billing-validator)
- [Official EN16931 Validation Artefacts](https://github.com/ConnectingEurope/eInvoicing-EN16931)
- [Peppol Practical - Online Validator](https://peppol.helger.com/public/menuitem-validation-ws2)
