#include <SPI.h>
#include "dw3000.h"
#include <WiFi.h>
#include <HTTPClient.h>

#define APP_NAME "SIMPLE RX v1.1"
#define FRAME_LENGTH (sizeof(tx_msg) + FCS_LEN)
#define ALL_MSG_COMMON_LEN 10
#define ALL_MSG_SN_IDX 1
#define FRAME_LEN_MAX 127
#define FCS_LEN 2

const uint8_t PIN_RST = 27;
const uint8_t PIN_IRQ = 34;
const uint8_t PIN_SS = 4;
static uint8_t rx_sync_msg[] = {0xC5, 0, 'S', 'Y', 'N', 'C', 0, 0, 0, 0};
static uint8_t rx_tag_msg[] = {0xC5, 0, 'T', 'A', 'G', 0, 0, 0, 0, 0};


// Wi-Fi credentials
const char* ssid = "AIoT_2F";
const char* password = "monetghgh";

// Server endpoint
const char* serverName = "http://127.0.0.1:5000";

/* Default communication configuration. We use default non-STS DW mode. */
static dwt_config_t config = {
  9, DWT_PLEN_128, DWT_PAC8, 9, 9, 1, DWT_BR_6M8, DWT_PHRMODE_STD, DWT_PHRRATE_STD, (129 + 8 - 8), DWT_STS_MODE_OFF, DWT_STS_LEN_64, DWT_PDOA_M0
};

static uint8_t rx_buffer[FRAME_LEN_MAX];
uint32_t status_reg;
uint16_t frame_len;

void setup() {
  UART_init();
  test_run_info((unsigned char*)APP_NAME);

  /* Configure SPI rate, DW3000 supports up to 38 MHz */
  /* Reset DW IC */
  spiBegin(PIN_IRQ, PIN_RST);
  spiSelect(PIN_SS);

  delay(200);

  while (!dwt_checkidlerc()) {
    UART_puts("IDLE FAILED\r\n");
    while (1);
  }

  dwt_softreset();
  delay(200);

  if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) {
    UART_puts("INIT FAILED\r\n");
    while (1);
  }

  dwt_setleds(DWT_LEDS_ENABLE | DWT_LEDS_INIT_BLINK);

  if (dwt_configure(&config)) {
    UART_puts("CONFIG FAILED\r\n");
    while (1);
  }

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connected");
}

void loop() {
  int frame_sn = 0;
  memset(rx_buffer, 0, sizeof(rx_buffer));
  dwt_rxenable(DWT_START_RX_IMMEDIATE);

  while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) & (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR))) {}

  if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
    frame_len = dwt_read32bitreg(RX_FINFO_ID) & RX_FINFO_RXFLEN_BIT_MASK;
    if (frame_len <= FRAME_LEN_MAX) {
      frame_sn = rx_buffer[ALL_MSG_SN_IDX];
      rx_buffer[ALL_MSG_SN_IDX] = 0;

      if (memcmp(rx_buffer, rx_sync_msg, ALL_MSG_COMMON_LEN) == 0) {
        test_run_info((unsigned char*)"Sync frame Received");
        uint64_t rx_sync_time = dwt_readrxtimestamplo32();
        Serial.print("Received Sync frame timestamp: ");
        Serial.println(rx_sync_time);
        sendTimestampsToServer("anchor1", rx_sync_time, "sync", frame_sn);
      }

      if (memcmp(rx_buffer, rx_tag_msg, ALL_MSG_COMMON_LEN) == 0) {
        test_run_info((unsigned char*)"Tag frame Received");
        uint64_t rx_tag_time = dwt_readrxtimestamplo32();
        Serial.print("Received Tag frame timestamp: ");
        Serial.println(rx_tag_time);
        sendTimestampsToServer("anchor1", rx_tag_time, "tag", frame_sn);
        Serial.println("Tag Timestamp Sent");
      }
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);

  } else {
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
  }
}

void sendTimestampsToServer(const char* anchor_id, uint64_t timestamp, const char* frame_type, int sequence_number) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;

    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    String payload = "{ \"anchor_id\": \"" + String(anchor_id) + "\", \"timestamp\": " + String(timestamp) + ", \"frame_type\": \"" + String(frame_type) + "\", \"sequence_number\": " + String(sequence_number) + " }";

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.println(httpResponseCode);
      Serial.println(response);
    } else {
      Serial.print("Error on sending POST: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  } else {
    Serial.println("Error in WiFi connection");
  }
}